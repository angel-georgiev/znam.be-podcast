/* Sticky podcast player. Any element with data-play-src starts that audio in the bar.
   Without JavaScript, those elements are links to the MP3 and still work. */
(function () {
  var root = document.getElementById('player');
  if (!root) return;
  var audio = root.querySelector('[data-audio]');
  var toggle = root.querySelector('[data-toggle]');
  var iconPlay = root.querySelector('[data-icon-play]');
  var iconPause = root.querySelector('[data-icon-pause]');
  var titleEl = root.querySelector('[data-title]');
  var cur = root.querySelector('[data-current]');
  var tot = root.querySelector('[data-total]');
  var seek = root.querySelector('[data-seek]');
  var current = null;

  function fmt(s) {
    if (!isFinite(s)) return '0:00';
    s = Math.floor(s);
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    var mm = h ? String(m).padStart(2, '0') : String(m);
    return (h ? h + ':' : '') + mm + ':' + String(sec).padStart(2, '0');
  }

  function syncButtons() {
    var playing = !audio.paused;
    iconPlay.hidden = playing;
    iconPause.hidden = !playing;
    toggle.setAttribute('aria-label', playing ? 'Пауза' : 'Пусни');
    document.querySelectorAll('[data-play-src]').forEach(function (b) {
      var on = current && b.getAttribute('data-play-src') === current.src && playing;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      var label = b.querySelector('[data-label]');
      if (label) label.textContent = on ? 'Пауза' : (b.getAttribute('data-label-idle') || 'Слушай');
    });
  }

  function load(item) {
    current = item;
    audio.src = item.src;
    titleEl.textContent = item.title;
    titleEl.href = item.url || item.src;
    root.hidden = false;
    if ('mediaSession' in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: item.title, artist: 'За Учителите', album: 'Знам.бе',
        artwork: item.art ? [{ src: item.art, sizes: '3000x3000', type: 'image/jpeg' }] : []
      });
    }
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-play-src]');
    if (!b) return;
    e.preventDefault();
    var src = b.getAttribute('data-play-src');
    if (current && current.src === src) {
      audio.paused ? audio.play() : audio.pause();
      return;
    }
    load({
      src: src,
      title: b.getAttribute('data-play-title'),
      url: b.getAttribute('data-play-url'),
      art: b.getAttribute('data-play-art')
    });
    audio.play();
  });

  toggle.addEventListener('click', function () { audio.paused ? audio.play() : audio.pause(); });
  root.querySelectorAll('[data-skip]').forEach(function (b) {
    b.addEventListener('click', function () {
      audio.currentTime = Math.max(0, Math.min((audio.duration || 0), audio.currentTime + Number(b.getAttribute('data-skip'))));
    });
  });
  seek.addEventListener('input', function () { audio.currentTime = Number(seek.value); });

  audio.addEventListener('loadedmetadata', function () { seek.max = Math.floor(audio.duration); tot.textContent = fmt(audio.duration); });
  audio.addEventListener('timeupdate', function () {
    cur.textContent = fmt(audio.currentTime);
    seek.value = Math.floor(audio.currentTime);
    seek.style.setProperty('--pct', (audio.duration ? (audio.currentTime / audio.duration) * 100 : 0) + '%');
    seek.setAttribute('aria-valuetext', fmt(audio.currentTime) + ' от ' + fmt(audio.duration));
  });
  audio.addEventListener('play', syncButtons);
  audio.addEventListener('pause', syncButtons);
  audio.addEventListener('ended', syncButtons);

  if ('mediaSession' in navigator) {
    navigator.mediaSession.setActionHandler('seekbackward', function () { audio.currentTime = Math.max(0, audio.currentTime - 15); });
    navigator.mediaSession.setActionHandler('seekforward', function () { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15); });
  }

  /* Arrow buttons for horizontal rows */
  document.querySelectorAll('.row-nav').forEach(function (nav) {
    var row = document.getElementById(nav.querySelector('[aria-controls]').getAttribute('aria-controls'));
    var btns = nav.querySelectorAll('[data-row-scroll]');
    function update() {
      btns[0].disabled = row.scrollLeft <= 2;
      btns[1].disabled = row.scrollLeft + row.clientWidth >= row.scrollWidth - 2;
    }
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        row.scrollBy({ left: Number(b.getAttribute('data-row-scroll')) * row.clientWidth * 0.8, behavior: 'smooth' });
      });
    });
    row.addEventListener('scroll', update, { passive: true });
    nav.hidden = false;
    update();
  });

  /* Copy-the-feed buttons */
  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function () {
        var label = b.querySelector('[data-label]');
        var old = label.textContent;
        label.textContent = 'Копирано';
        setTimeout(function () { label.textContent = old; }, 1600);
      });
    });
  });
})();
