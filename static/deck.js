/* 星声 —— 三页叠放：变调 / 乐器欣赏 / 活动分享 */
(function () {
  var deck = document.querySelector('.deck');
  if (!deck) return;

  var tabs = Array.prototype.slice.call(deck.querySelectorAll('.deck-tab'));
  var pages = Array.prototype.slice.call(deck.querySelectorAll('.page'));
  var tabbar = deck.querySelector('.deck-tabs');
  if (!tabs.length || !pages.length) return;

  function indexOfPage(name) {
    for (var i = 0; i < pages.length; i++) {
      if (pages[i].dataset.page === name) return i;
    }
    return -1;
  }

  function show(name, opts) {
    var target = indexOfPage(name);
    if (target < 0) return;

    pages.forEach(function (p, i) {
      var active = i === target;
      p.classList.toggle('is-active', active);
      p.setAttribute('aria-hidden', active ? 'false' : 'true');
      if (active) {
        p.style.zIndex = '9';
        p.style.removeProperty('--d');
      } else {
        var d = (i - target + pages.length) % pages.length;
        p.style.setProperty('--d', String(d));
        p.style.zIndex = String(9 - d);
      }
    });

    tabs.forEach(function (t) {
      var on = t.dataset.page === name;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
    });

    // 换页后把整叠拉到视口顶部：长页面里切页才不会停在半空
    if (opts && opts.scroll) {
      var rect = deck.getBoundingClientRect();
      if (rect.top < -8 || rect.top > 120) {
        deck.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }

  window.deckShow = show;

  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      show(t.dataset.page, { scroll: true });
    });
  });

  if (tabbar) {
    tabbar.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      var cur = tabs.findIndex(function (t) { return t.classList.contains('is-active'); });
      if (cur < 0) cur = 0;
      var next = (cur + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      show(tabs[next].dataset.page, { scroll: true });
      tabs[next].focus();
      e.preventDefault();
    });
  }

  // 「拿去变调」「换个调再变一次」「历史里试听」这些动作会滚到 #lab，
  // 先在三页里把「变调」翻上来，用户才看得到。
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    if (t.closest('#genShift, #newShiftBtn, #genHistory button, #genHistory a')) {
      show('lab');
    }
  }, true);

  show('lab');
})();
