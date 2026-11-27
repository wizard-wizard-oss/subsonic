"use strict";
/* Éditeur de tags : un seul ouvert à la fois. */
const AlbumTagsEditor = (() => {
  const {Editor, state} = AlbumTags;

  function open(album, onSaved) {
    if (!App.can("coverArt")) return;
    if (state.current) { state.current.requestClose(); return; }
    state.current = new Editor(album, onSaved); state.current.mount();
  }

  return {open, destroy: () => { if (state.current) state.current.close(); }};
})();
