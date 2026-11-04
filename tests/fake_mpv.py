"""Faux mpv pour les tests : écoute sur un socket Unix et parle le protocole JSON d'mpv (sous-ensemble).
Usage : python3 tests/fake_mpv.py --input-ipc-server=CHEMIN  (les autres options sont ignorées)"""
import json
import socket
import sys
import threading


def main():
    path = next(a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--input-ipc-server="))
    log_path = path + ".log"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    conn, _ = server.accept()
    observed = {}
    playlist = []
    lock = threading.Lock()

    def send(message):
        with lock:
            conn.sendall((json.dumps(message) + "\n").encode())

    def change(name, data):
        if name in observed:
            send({"event": "property-change", "id": observed[name], "name": name, "data": data})

    buffer = b""
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            message = json.loads(line)
            command = message["command"]
            with open(log_path, "a") as log:
                log.write(json.dumps(command) + "\n")
            if command[0] == "observe_property":
                observed[command[2]] = command[1]
                change(command[2], {"idle-active": True, "pause": False}.get(command[2]))
                continue
            data = None
            if command[0] == "loadfile":
                if command[2] == "replace":
                    playlist[:] = [command[1]]
                    change("idle-active", False)
                    change("duration", 261.0)
                    change("time-pos", 0.0)
                else:
                    playlist.append(command[1])
            elif command[0] == "playlist-clear":
                del playlist[1:]
            elif command[0] == "set_property" and command[1] == "pause":
                change("pause", command[2])
            elif command[0] == "seek":
                change("time-pos", float(command[1]))
            elif command[0] == "test-finish":            # le titre en cours se termine (pour les tests)
                send({"event": "end-file", "reason": "eof"})
                playlist.pop(0)
                if not playlist:
                    change("idle-active", True)
            elif command[0] == "test-fail":
                send({"event": "end-file", "reason": "error"})
            elif command[0] == "get_property" and command[1] == "playlist":
                data = playlist
            if "request_id" in message:
                send({"request_id": message["request_id"], "error": "success", "data": data})


if __name__ == "__main__":
    main()
