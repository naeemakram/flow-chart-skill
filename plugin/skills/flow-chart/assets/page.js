(function () {
  var DOC = JSON.parse(document.getElementById('objdata').textContent);
  var OBJ = DOC.objects;
  var tip = document.getElementById('tip');
  var toastEl = document.getElementById('toast');
  var tray = document.getElementById('tray');
  var trayText = document.getElementById('traytext');
  var manyBox = document.getElementById('many');
  var picked = [];
  var toastTimer, tipTimer;

  function el(oid) { return document.querySelector('[data-oid="' + oid + '"]'); }
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
  function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

  /* The text a person pastes to the AI: enough to find the object even without the page open. */
  function refLine(oid) {
    var o = OBJ[oid];
    if (!o) return oid;
    if (o.k === 'line') {
      var ends = o.f && o.o ? ' ' + o.f + ' -> ' + o.o : '';
      return oid + ' [line' + (o.r ? ': ' + o.r : '') + ']' + ends + ' "' + o.t + '"';
    }
    return oid + ' [' + o.k + '] "' + o.t + '"';
  }
  function refBlock(ids) {
    return 'In "' + DOC.title + '":\n' + ids.map(refLine).join('\n');
  }

  function toast(text) {
    toastEl.textContent = text;
    toastEl.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('on'); }, 1800);
  }
  /* Clipboard API first; it is missing or refused in some sandboxes, so fall back to a hidden textarea. */
  function copyText(text, done) {
    function legacy() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) {}
      ta.remove();
      toast(ok ? done : 'Could not copy: ' + text.slice(0, 120));
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(done); }, legacy);
    } else {
      legacy();
    }
  }

  function showTip(oid, x, y, anchor) {
    var o = OBJ[oid];
    if (!o) return;
    tip.textContent = '';
    function add(cls, text) {
      var s = document.createElement('span');
      s.className = cls;
      s.textContent = text;
      tip.appendChild(s);
    }
    add('tid', oid + ' · ' + o.k + (o.r ? ' (' + o.r + ')' : ''));
    add('tname', o.t);
    if (o.f && o.o) add('tsrc', o.f + ' → ' + o.o);
    if (o.d) tip.appendChild(document.createTextNode(o.d));
    if (o.s) add('tsrc', o.s);
    add('thint', 'Click to copy · Shift-click to collect');
    tip.hidden = false;
    var r = tip.getBoundingClientRect();
    if (anchor) {
      var a = anchor.getBoundingClientRect();
      x = a.left + a.width / 2;
      y = a.bottom;
    }
    var left = Math.min(Math.max(8, x + 14), window.innerWidth - r.width - 8);
    var top = y + 16;
    if (top + r.height > window.innerHeight - 8) top = Math.max(8, y - r.height - 12);
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  function hideTip() { tip.hidden = true; }

  function setRelated(oid, on) {
    var o = OBJ[oid];
    if (!o) return;
    var ids = [];
    if (o.m) ids = ids.concat(o.m);
    if (o.k === 'set') {
      Object.keys(OBJ).forEach(function (k) {
        if (OBJ[k].m && OBJ[k].m.indexOf(oid) >= 0) ids.push(k);
      });
    }
    if (o.f) ids.push(o.f);
    if (o.o) ids.push(o.o);
    if (o.k !== 'line') {
      Object.keys(OBJ).forEach(function (k) {
        if (OBJ[k].k === 'line' && (OBJ[k].f === oid || OBJ[k].o === oid)) ids.push(k);
      });
    }
    ids.forEach(function (id) {
      var e = el(id);
      if (e) e.classList.toggle('rel', on);
    });
  }

  function togglePick(oid) {
    var i = picked.indexOf(oid);
    if (i >= 0) picked.splice(i, 1); else picked.push(oid);
    var e = el(oid);
    if (e) e.classList.toggle('picked', i < 0);
    tray.hidden = picked.length === 0;
    trayText.textContent = picked.length + ' collected: ' + picked.join(', ');
  }
  function clearPicks() { picked.slice().forEach(togglePick); }

  function objectOf(target) {
    if (!target || !target.closest) return null;
    var e = target.closest('[data-oid]');
    /* A figure carries an ID, but hovering empty space in it isn't pointing at anything. */
    return e && e.tagName.toLowerCase() !== 'figure' ? e : null;
  }

  var current = null;
  document.addEventListener('mousemove', function (ev) {
    var e = objectOf(ev.target);
    var oid = e ? e.getAttribute('data-oid') : null;
    if (oid !== current) {
      if (current) setRelated(current, false);
      if (oid) setRelated(oid, true);
      current = oid;
    }
    if (oid) showTip(oid, ev.clientX, ev.clientY); else hideTip();
  });
  document.addEventListener('focusin', function (ev) {
    var e = objectOf(ev.target);
    if (e && ev.target === e) showTip(e.getAttribute('data-oid'), 0, 0, e);
  });
  document.addEventListener('focusout', hideTip);
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') { hideTip(); return; }
    if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches && ev.target.matches('[data-oid]')) {
      ev.preventDefault();
      activate(ev.target.getAttribute('data-oid'), ev.shiftKey || ev.ctrlKey || ev.metaKey, ev.target);
    }
  });

  function activate(oid, collect, anchor) {
    if (collect || manyBox.checked) {
      togglePick(oid);
      return;
    }
    copyText(refLine(oid), 'Copied ' + oid);
    /* Touch screens have no hover, so a tap also shows the tooltip for a moment. */
    showTip(oid, 0, 0, anchor);
    clearTimeout(tipTimer);
    tipTimer = setTimeout(hideTip, 4000);
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    var chip = t.closest && t.closest('[data-copy]');
    if (chip) {
      var id = chip.getAttribute('data-copy');
      if (ev.shiftKey || ev.ctrlKey || ev.metaKey || manyBox.checked) togglePick(id);
      else copyText(refLine(id), 'Copied ' + id);
      ev.stopPropagation();
      return;
    }
    var scope = t.closest && t.closest('[data-copy-scope]');
    if (scope) {
      var pre = scope.getAttribute('data-copy-scope');
      var ids = Object.keys(OBJ).filter(function (k) { return k === pre || k.indexOf(pre + '.') === 0; });
      copyText(refBlock(ids), 'Copied ' + ids.length + ' objects from ' + pre);
      return;
    }
    var e = objectOf(t);
    if (!e) return;
    var collect = ev.shiftKey || ev.ctrlKey || ev.metaKey;
    /* Selecting table text to copy it shouldn't also copy the row. A shift-click selects text too, but means collect. */
    if (!collect && String(window.getSelection())) return;
    activate(e.getAttribute('data-oid'), collect, e);
  });
  document.addEventListener('mousedown', function (ev) {
    if (ev.shiftKey && objectOf(ev.target)) ev.preventDefault();
  });

  document.getElementById('copyall').addEventListener('click', function () {
    var ids = Object.keys(OBJ);
    copyText(refBlock(ids), 'Copied all ' + ids.length + ' IDs');
  });
  document.getElementById('traycopy').addEventListener('click', function () {
    copyText(refBlock(picked), 'Copied ' + picked.length + ' objects');
  });
  document.getElementById('trayclear').addEventListener('click', clearPicks);

  function goTo(oid) {
    var e = el(oid) || document.getElementById(oid);
    if (!e) return false;
    var details = e.closest && e.closest('details');
    if (details) details.open = true;
    e.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
    e.classList.remove('flash');
    void e.getBoundingClientRect();
    e.classList.add('flash');
    setTimeout(function () { e.classList.remove('flash'); }, 2300);
    return true;
  }
  document.getElementById('find').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var q = document.getElementById('findbox').value.trim().toLowerCase();
    if (!q) return;
    var all = Object.keys(OBJ);
    var exact = all.filter(function (k) { return k.toLowerCase() === q; });
    /* "B7" alone is fine when only one figure has a B7. */
    var hits = exact.length ? exact : all.filter(function (k) {
      return k.toLowerCase().slice(-q.length - 1) === '.' + q;
    });
    if (hits.length === 1) {
      goTo(hits[0]);
      history.replaceState(null, '', '#' + hits[0]);
    } else if (hits.length > 1) {
      toast('Which one? ' + hits.join(', '));
    } else {
      toast('No object called ' + q);
    }
  });

  var showIds = document.getElementById('showids');
  function applyIds() { document.body.classList.toggle('noids', !showIds.checked); }
  if (recall('flowchart-ids') === 'off') showIds.checked = false;
  applyIds();
  showIds.addEventListener('change', function () {
    applyIds();
    store('flowchart-ids', showIds.checked ? 'on' : 'off');
  });

  function fromHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    if (id && OBJ[id]) setTimeout(function () { goTo(id); }, 150);
  }
  window.addEventListener('hashchange', fromHash);
  fromHash();
})();
