"""Écritures réelles sur petites fixtures audio, sans bibliothèque ni réseau externes."""
import hashlib
import json
import os
import shutil
import stat
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from mutagen.flac import FLAC, Picture
from mutagen.aiff import AIFF
from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, TXXX, TYER
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

from pimedia.webapp.tags.audio import (AudioFileEdit, AudioTagError, AudioTags, FIELDS,
                                       MAX_BACKUP_OPERATIONS, validate_changes)

PAYLOAD = b"\xff\xfb\x90\x00" + bytes(413)
PCM = bytes(range(128)) * 4


def make_mp3(path, version=4):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PAYLOAD * 8)
    tags = ID3()
    tags.add(TIT2(encoding=1 if version == 3 else 3, text=["Titre initial"]))
    tags.add(TPE1(encoding=1 if version == 3 else 3, text=["Artiste", "Invitée"]))
    tags.add(TPE2(encoding=1 if version == 3 else 3, text=["Artiste album"]))
    tags.add(TALB(encoding=1 if version == 3 else 3, text=["Album"]))
    tags.add(TRCK(encoding=1 if version == 3 else 3, text=["1/12"]))
    tags.add(TCON(encoding=1 if version == 3 else 3, text=["Rock", "Experimental"]))
    tags.add((TYER if version == 3 else TDRC)(encoding=1 if version == 3 else 3, text=["2021"]))
    tags.add(TXXX(encoding=1 if version == 3 else 3, desc="replaygain_track_gain", text=["-3 dB"]))
    tags.add(APIC(encoding=0, mime="image/png", type=3, desc="cover", data=b"image-payload"))
    tags.save(path, v2_version=version)


def make_flac(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    packed = (44100 << 44) | (1 << 41) | (15 << 36) | 64
    streaminfo = struct.pack(">HH", 16, 16) + bytes(6) + packed.to_bytes(8, "big") + bytes(16)
    path.write_bytes(b"fLaC\x80\x00\x00\x22" + streaminfo + b"flac-audio-payload")
    audio = FLAC(path)
    audio["title"] = ["Titre initial"]
    audio["artist"] = ["Artiste", "Invitée"]
    audio["albumartist"] = ["Artiste album"]
    audio["genre"] = ["Rock", "Experimental"]
    audio["date"] = ["2021-05-04"]
    audio["tracknumber"] = ["1/12"]
    audio["replaygain_track_gain"] = ["-3 dB"]
    cover = Picture()
    cover.type, cover.mime, cover.data = 3, "image/png", b"image-payload"
    audio.add_picture(cover)
    audio.save()


def _ogg_page(packet, sequence, flags=0, granule=0):
    sizes = bytes([255] * (len(packet) // 255) + [len(packet) % 255])
    data = bytearray(b"OggS\x00" + bytes([flags]) + struct.pack("<QII", granule, 12, sequence)
                     + bytes(4) + bytes([len(sizes)]) + sizes + packet)
    checksum = 0
    for value in data:
        checksum ^= value << 24
        for _ in range(8):
            checksum = ((checksum << 1) ^ (0x04C11DB7 if checksum & 0x80000000 else 0)) & 0xFFFFFFFF
    data[22:26] = struct.pack("<I", checksum)
    return data


def make_ogg(path, opus=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    vendor = b"tag-tests"
    comments = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0)
    if opus:
        packets = [b"OpusHead\x01\x02" + struct.pack("<HIhB", 0, 48000, 0, 0), b"OpusTags" + comments,
                   b"\x98opus-audio-payload"]
    else:
        packets = [b"\x01vorbis" + struct.pack("<IBIiiiBB", 0, 2, 44100, 0, 128000, 0, 0xB8, 1),
                   b"\x03vorbis" + comments + b"\x01", b"\x05vorbis-setup", b"vorbis-audio-payload"]
    path.write_bytes(b"".join(_ogg_page(packet, index, 2 if index == 0 else 4 if index == len(packets)-1 else 0,
                                      1000 if index == len(packets)-1 else 0)
                              for index, packet in enumerate(packets)))
    audio = (OggOpus if opus else OggVorbis)(path)
    audio["title"], audio["genre"], audio["artist"] = ["Titre initial"], ["Rock"], ["Artiste", "Invitée"]
    audio["replaygain_track_gain"] = ["-3 dB"]
    audio.save()


def make_mp4(path):
    def atom(kind, body):
        return struct.pack(">I", len(body) + 8) + kind + body
    path.parent.mkdir(parents=True, exist_ok=True)
    hdlr = atom(b"hdlr", bytes(8) + b"soun" + bytes(12))
    mdhd = atom(b"mdhd", bytes(12) + struct.pack(">II", 44100, 44100) + bytes(4))
    track = atom(b"trak", atom(b"mdia", hdlr + mdhd))
    path.write_bytes(atom(b"ftyp", b"M4A " + bytes(4) + b"M4A ") + atom(b"moov", track)
                     + atom(b"mdat", b"mp4-audio-payload"))
    audio = MP4(path)
    audio.add_tags()
    audio["\xa9nam"], audio["\xa9ART"], audio["trkn"] = ["Titre initial"], ["Artiste", "Invitée"], [(1, 12)]
    audio["\xa9day"] = ["2021-05-04"]
    audio["covr"] = [MP4Cover(b"image-payload", imageformat=MP4Cover.FORMAT_PNG)]
    audio["----:com.apple.iTunes:replaygain_track_gain"] = [b"-3 dB"]
    audio.save()


class AudioTagsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="audio-tags-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "music"
        self.root.mkdir()
        self.backups = Path(self.tmp.name).resolve() / "backups"
        self.writer = AudioTags(str(self.root), str(self.backups))

    def file(self, name="Artist/Album/01.mp3", version=4):
        path = self.root / name
        make_mp3(path, version)
        return path

    def edit(self, relative="Artist/Album/01.mp3", **changes):
        snapshot = self.writer.inspect(relative)
        return AudioFileEdit(relative, snapshot.revision, changes)

    def test_mp3_preserves_audio_unknown_fields_picture_multivalues_and_totals(self):
        path = self.file()
        snapshot = self.writer.inspect("Artist/Album/01.mp3")
        self.assertEqual(snapshot.tags["artist"], "Artiste; Invitée")
        self.assertTrue(snapshot.editable)
        self.assertEqual(snapshot.format, "mp3")
        self.writer.apply((self.edit(title="Titre corrigé", track="2"),))
        tags = ID3(path, translate=False)
        self.assertEqual(str(tags["TIT2"]), "Titre corrigé")
        self.assertEqual(str(tags["TRCK"]), "2/12")
        self.assertEqual(tags["TPE1"].text, ["Artiste", "Invitée"])
        self.assertEqual(tags["TCON"].text, ["Rock", "Experimental"])
        self.assertEqual(tags["APIC:cover"].data, b"image-payload")
        self.assertEqual(str(tags["TXXX:replaygain_track_gain"]), "-3 dB")
        self.assertIn(PAYLOAD * 8, path.read_bytes())
        self.assertEqual(self.writer.inspect("Artist/Album/01.mp3").tags["track"], "2")
        self.assertNotEqual(snapshot.revision, self.writer.inspect("Artist/Album/01.mp3").revision)

    def test_id3v23_remains_v23_and_uses_year_frame(self):
        path = self.file(version=3)
        self.writer.apply((self.edit(title="Été", year="2024"),))
        tags = ID3(path, translate=False)
        self.assertEqual(tags.version[1], 3)
        self.assertEqual(str(tags["TYER"]), "2024")
        self.assertEqual(str(tags["TIT2"]), "Été")
        self.assertIn(PAYLOAD * 8, path.read_bytes())

    def test_flac_preserves_images_audio_and_date_precision(self):
        path = self.root / "Artist/Album/01.flac"
        make_flac(path)
        self.writer.apply((self.edit("Artist/Album/01.flac", year="2024", title="Nouveau titre"),))
        audio = FLAC(path)
        self.assertEqual(audio["date"], ["2024-05-04"])
        self.assertEqual(audio["artist"], ["Artiste", "Invitée"])
        self.assertEqual(audio["genre"], ["Rock", "Experimental"])
        self.assertEqual(audio.pictures[0].data, b"image-payload")
        self.assertEqual(audio["replaygain_track_gain"], ["-3 dB"])
        self.assertTrue(path.read_bytes().endswith(b"flac-audio-payload"))

    def test_ogg_vorbis_and_opus(self):
        for opus in (False, True):
            with self.subTest(opus=opus):
                relative = "Artist/Album/01." + ("opus" if opus else "ogg")
                path = self.root / relative
                make_ogg(path, opus)
                self.writer.apply((self.edit(relative, genre="Jazz", title="Titre corrigé"),))
                audio = (OggOpus if opus else OggVorbis)(path)
                self.assertEqual(audio["genre"], ["Jazz"])
                self.assertEqual(audio["artist"], ["Artiste", "Invitée"])
                self.assertEqual(audio["replaygain_track_gain"], ["-3 dB"])
                self.assertIn(b"audio-payload", path.read_bytes())

    def test_wave_tags_preserve_pcm(self):
        path = self.root / "Artist/Album/01.wav"
        path.parent.mkdir(parents=True)
        with wave.open(str(path), "wb") as target:
            target.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
            target.writeframes(PCM)
        audio = WAVE(path)
        audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text=["Titre initial"]))
        audio.tags.add(TXXX(encoding=3, desc="keep", text=["intact"]))
        audio.save()
        self.writer.apply((self.edit("Artist/Album/01.wav", title="Titre corrigé"),))
        with wave.open(str(path), "rb") as source:
            self.assertEqual(source.readframes(source.getnframes()), PCM)
        self.assertEqual(str(WAVE(path).tags["TXXX:keep"]), "intact")

    def test_aiff_preserves_pcm_and_id3_version(self):
        path = self.root / "Artist/Album/01.aiff"
        path.parent.mkdir(parents=True)
        comm = struct.pack(">hIh", 2, len(PCM)//4, 16) + bytes.fromhex("400eac44000000000000")
        chunks = b"COMM" + struct.pack(">I", len(comm)) + comm + b"SSND" + struct.pack(">I", len(PCM)+8) + bytes(8) + PCM
        path.write_bytes(b"FORM" + struct.pack(">I", len(chunks)+4) + b"AIFF" + chunks)
        audio = AIFF(path)
        audio.add_tags()
        audio.tags.add(TIT2(encoding=1, text=["Titre initial"]))
        audio.tags.add(TYER(encoding=1, text=["2021"]))
        audio.save(v2_version=3)
        self.writer.apply((self.edit("Artist/Album/01.aiff", title="Titre corrigé", year="2024"),))
        self.assertIn(PCM, path.read_bytes())
        self.assertEqual(AIFF(path).tags.version[1], 3)
        self.assertEqual(self.writer.inspect("Artist/Album/01.aiff").tags["year"], "2024")

    def test_mp4_preserves_audio_picture_total_and_unknown_atoms(self):
        path = self.root / "Artist/Album/01.m4a"
        make_mp4(path)
        self.writer.apply((self.edit("Artist/Album/01.m4a", title="Titre corrigé", year="2024", track="2"),))
        audio = MP4(path)
        self.assertEqual(audio["\xa9nam"], ["Titre corrigé"])
        self.assertEqual(audio["\xa9day"], ["2024-05-04"])
        self.assertEqual(audio["trkn"], [(2, 12)])
        self.assertEqual(audio["covr"], [b"image-payload"])
        self.assertEqual(audio["\xa9ART"], ["Artiste", "Invitée"])
        self.assertEqual(audio["----:com.apple.iTunes:replaygain_track_gain"], [b"-3 dB"])
        self.assertIn(b"mp4-audio-payload", path.read_bytes())

    def test_clearing_field_is_explicit_and_other_tags_survive(self):
        path = self.file()
        self.writer.apply((self.edit(genre=""),))
        self.assertNotIn("TCON", ID3(path))
        self.assertIn("TPE1", ID3(path))

    def test_paths_symlinks_and_hardlinks_rejected(self):
        path = self.file()
        for relative in ("/etc/passwd", "../elsewhere", "Artist/./Album/01.mp3", "Artist\\Album\\01.mp3"):
            with self.subTest(relative=relative), self.assertRaisesRegex(AudioTagError, "tags.unsafe_path"):
                self.writer.inspect(relative)
        (self.root / "link.mp3").symlink_to(path)
        (self.root / "linked").symlink_to(path.parent)
        for relative in ("link.mp3", "linked/01.mp3"):
            with self.assertRaisesRegex(AudioTagError, "tags.unsafe_path"):
                self.writer.inspect(relative)
        os.link(path, self.root / "hardlink.mp3")
        with self.assertRaisesRegex(AudioTagError, "tags.unsafe_path"):
            self.writer.inspect("Artist/Album/01.mp3")

    def test_file_changed_since_snapshot_is_never_overwritten(self):
        path = self.file()
        edit = self.edit(title="Correction")
        with open(path, "ab") as target:
            target.write(b"external-change")
        before = path.read_bytes()
        with self.assertRaisesRegex(AudioTagError, "tags.conflict"):
            self.writer.apply((edit,))
        self.assertEqual(path.read_bytes(), before)

    def test_readonly_or_unrecognised_file_has_explicit_reason(self):
        path = self.root / "raw.aac"
        path.write_bytes(b"not-an-audio-container")
        snapshot = self.writer.inspect("raw.aac")
        self.assertFalse(snapshot.editable)
        self.assertIn(snapshot.reason, ("tags.unsupported_format", "tags.unreadable_file"))
        self.assertEqual(set(snapshot.tags), set(FIELDS))

    def test_all_files_prepared_before_any_publication(self):
        first, second = self.file(), self.file("Artist/Album/02.mp3")
        before = first.read_bytes(), second.read_bytes()
        edits = self.edit(title="One"), self.edit("Artist/Album/02.mp3", title="Two")
        original = self.writer._copy
        def fail_second(source, destination):
            if str(source).endswith("02.mp3"):
                raise OSError("copy failed")
            original(source, destination)
        with patch.object(self.writer, "_copy", side_effect=fail_second):
            with self.assertRaisesRegex(AudioTagError, "tags.write_failed"):
                self.writer.apply(edits)
        self.assertEqual((first.read_bytes(), second.read_bytes()), before)
        self.assertFalse(list(first.parent.glob(".pimedia-tags-*")))
        self.writer.recover()

    def test_progress_reports_preparation_before_publication(self):
        first, second = self.file(), self.file("Artist/Album/02.mp3")
        before = first.read_bytes(), second.read_bytes()
        edits = self.edit(title="One"), self.edit("Artist/Album/02.mp3", title="Two")
        updates = []
        def progress(phase, completed, total):
            updates.append((phase, completed, total))
            if phase == "preparing" or not completed:
                self.assertEqual((first.read_bytes(), second.read_bytes()), before)
            elif completed == 1:
                self.assertEqual(str(ID3(first)["TIT2"]), "One")
                self.assertEqual(second.read_bytes(), before[1])
        self.writer.apply(edits, progress=progress)
        self.assertEqual(updates, [("preparing", 0, 2), ("preparing", 1, 2), ("preparing", 2, 2),
                                   ("publishing", 0, 2), ("publishing", 1, 2), ("publishing", 2, 2)])
        self.assertEqual(str(ID3(second)["TIT2"]), "Two")
        self.writer.recover()

    def test_failed_second_publication_restores_first(self):
        first, second = self.file(), self.file("Artist/Album/02.mp3")
        before = first.read_bytes(), second.read_bytes()
        edits = self.edit(title="One"), self.edit("Artist/Album/02.mp3", title="Two")
        replace = os.replace
        failed = False
        def fail_second(source, destination):
            nonlocal failed
            if str(destination) == str(second) and not failed:
                failed = True
                raise OSError("replace failed")
            replace(source, destination)
        with patch("pimedia.webapp.tags.audio.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(AudioTagError, "tags.write_failed"):
                self.writer.apply(edits)
        self.assertEqual((first.read_bytes(), second.read_bytes()), before)
        self.assertFalse(list(first.parent.glob(".pimedia-tags-*")))
        self.writer.recover()

    def test_external_change_after_publication_is_preserved_during_rollback(self):
        path = self.file()
        def external_change(phase, completed, total):
            if phase != "publishing" or not completed:
                return
            with open(path, "ab") as target:
                target.write(b"external-change")
            raise OSError("interrupt after publication")
        with self.assertRaisesRegex(AudioTagError, "tags.recovery_required"):
            self.writer.apply((self.edit(title="Corrected"),), progress=external_change)
        self.assertTrue(path.read_bytes().endswith(b"external-change"))
        self.assertEqual(str(ID3(path)["TIT2"]), "Corrected")
        with self.assertRaisesRegex(AudioTagError, "tags.recovery_required"):
            self.writer.recover()

    def test_recovery_handles_crash_between_replace_and_manifest_update(self):
        path = self.file()
        before = path.read_bytes()
        class Crash(BaseException):
            pass
        sync = self.writer._sync_directory
        def crash_on_publication(folder):
            if folder == str(path.parent):
                raise Crash()
            sync(folder)
        with patch.object(self.writer, "_sync_directory", side_effect=crash_on_publication), \
             patch.object(self.writer, "_rollback", side_effect=Crash):
            with self.assertRaises(Crash):
                self.writer.apply((self.edit(title="Corrected"),))
        self.assertEqual(str(ID3(path)["TIT2"]), "Corrected")
        AudioTags(str(self.root), str(self.backups)).recover()
        self.assertEqual(path.read_bytes(), before)

    def test_backups_have_no_tag_values_and_stay_outside_music(self):
        self.file()
        self.writer.apply((self.edit(title="Private correction"),))
        manifest = next(self.backups.glob("*/manifest.json")).read_text()
        self.assertNotIn("Private correction", manifest)
        self.assertNotIn("Titre initial", manifest)
        self.assertEqual(json.loads(manifest)["state"], "committed")
        bad = AudioTags(str(self.root), str(self.root / ".backups"))
        with self.assertRaisesRegex(AudioTagError, "tags.unsafe_backup"):
            bad.apply((self.edit(title="No"),))

    def test_mode_and_ownership_are_preserved(self):
        path = self.file()
        path.chmod(0o640)
        before = path.stat()
        self.writer.apply((self.edit(title="Corrected"),))
        after = path.stat()
        self.assertEqual(stat.S_IMODE(after.st_mode), 0o640)
        self.assertEqual((after.st_uid, after.st_gid), (before.st_uid, before.st_gid))

    def test_invalid_values_are_rejected_before_writing(self):
        path = self.file()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        for changes in ({}, {"unknown":"value"}, {"title":None}, {"title":"bad\nvalue"},
                        {"year":"22"}, {"track":"0"}, {"disc":"1000"}, {"track":"2/12"}):
            with self.subTest(changes=changes), self.assertRaises(AudioTagError):
                validate_changes(changes)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_duplicate_paths_and_empty_batches_are_rejected(self):
        self.file()
        edit = self.edit(title="Corrected")
        for edits in ((), (edit, edit)):
            with self.assertRaisesRegex(AudioTagError, "tags.invalid_changes"):
                self.writer.apply(edits)

    def test_no_space_fails_before_preparing_files(self):
        path = self.file()
        before = path.read_bytes()
        free = shutil._ntuple_diskusage(100, 99, 1)
        with patch("pimedia.webapp.tags.files.shutil.disk_usage", return_value=free):
            with self.assertRaisesRegex(AudioTagError, "tags.no_space"):
                self.writer.apply((self.edit(title="Corrected"),))
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
