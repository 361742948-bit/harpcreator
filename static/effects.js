/* 星声 —— 光标星尘：鼠标划过时撒出流动的小星星 */
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var COLORS = ['#8B76FF', '#B39DFF', '#D9C6FF', '#C9A227', '#E8C87A', '#FFC9E4'];
  var MAX = 90;
  var layer = document.createElement('div');
  layer.className = 'spark-layer';
  document.body.appendChild(layer);

  var live = [];
  var last = { x: -1, y: -1, t: 0 };

  function spawn(x, y, energy) {
    var s = document.createElement('i');
    s.className = 'spark';
    var size = 6 + Math.random() * 10 * energy;
    var color = COLORS[(Math.random() * COLORS.length) | 0];
    var dx = (Math.random() - 0.5) * 26;
    var dy = -8 - Math.random() * 26;

    s.style.left = x + 'px';
    s.style.top = y + 'px';
    s.style.width = size + 'px';
    s.style.height = size + 'px';
    s.style.color = color;
    s.style.setProperty('--dx', dx.toFixed(1) + 'px');
    s.style.setProperty('--dy', dy.toFixed(1) + 'px');
    s.style.setProperty('--rot', ((Math.random() * 180) | 0) + 'deg');
    s.style.animationDuration = (620 + Math.random() * 420) + 'ms';

    layer.appendChild(s);
    live.push(s);

    if (live.length > MAX) {
      var old = live.shift();
      if (old && old.parentNode) old.parentNode.removeChild(old);
    }

    s.addEventListener('animationend', function () {
      if (s.parentNode) s.parentNode.removeChild(s);
      var i = live.indexOf(s);
      if (i > -1) live.splice(i, 1);
    });
  }

  function trail(e) {
    var now = performance.now();
    if (now - last.t < 16) return;

    var x = e.clientX;
    var y = e.clientY;

    if (last.x < 0) {
      spawn(x, y, 1);
    } else {
      var dist = Math.hypot(x - last.x, y - last.y);
      var steps = Math.min(6, Math.max(1, Math.round(dist / 14)));
      for (var i = 1; i <= steps; i++) {
        var t = i / steps;
        spawn(
          last.x + (x - last.x) * t + (Math.random() - 0.5) * 6,
          last.y + (y - last.y) * t + (Math.random() - 0.5) * 6,
          0.55 + Math.min(1, dist / 260) * 0.75
        );
      }
    }

    last.x = x; last.y = y; last.t = now;
  }

  window.addEventListener('pointermove', trail, { passive: true });
  window.addEventListener('pointerleave', function () { last.x = -1; last.y = -1; });
})();
