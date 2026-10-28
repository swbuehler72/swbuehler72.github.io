// Fills the "Real-time update" section of /now with the current location
// (Overland) and latest Swarm check-in, served by the Raspberry Pi.
(function () {
  var ENDPOINT = 'https://pi.swb72.us/now.json';

  function ago(iso) {
    var secs = (Date.now() - new Date(iso).getTime()) / 1000;
    if (secs < 60) return 'just now';
    var units = [[86400, 'day'], [3600, 'hour'], [60, 'minute']];
    for (var i = 0; i < units.length; i++) {
      if (secs >= units[i][0] && secs < 7 * 86400) {
        var n = Math.floor(secs / units[i][0]);
        return n + ' ' + units[i][1] + (n === 1 ? '' : 's') + ' ago';
      }
    }
    return 'on ' + new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  }

  function el(tag, text, className) {
    var e = document.createElement(tag);
    if (text) e.textContent = text;
    if (className) e.className = className;
    return e;
  }

  function when(iso, prefix) {
    var span = el('span', null, 'now-when');
    var t = el('time', ago(iso));
    t.dateTime = iso;
    t.title = new Date(iso).toLocaleString();
    span.append(' (' + (prefix || ''), t, ')');
    return span;
  }

  function fill(id, build) {
    var target = document.getElementById(id);
    if (!target) return;
    target.replaceChildren.apply(target, build());
  }

  fetch(ENDPOINT)
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      fill('now-location', function () {
        var l = data.location;
        if (!l) return ['Location unavailable.'];
        var out = [el('span', l.place || 'Somewhere on the map')];
        if (l.activity) out.push(' ', el('span', l.activity.charAt(0).toUpperCase() + l.activity.slice(1), 'now-activity'));
        out.push(when(l.time, 'as of '));
        return out;
      });
      fill('now-checkin', function () {
        var c = data.checkin;
        if (!c) return ['No recent check-ins.'];
        var out = [el('strong', c.venue)];
        if (c.category) out.push(' ', el('span', c.category, 'now-category'));
        if (c.locality) out.push(el('br'), el('span', c.locality));
        out.push(when(c.time));
        return out;
      });
    })
    .catch(function () {
      fill('now-location', function () { return ['Currently unavailable.']; });
      fill('now-checkin', function () { return ['Currently unavailable.']; });
    });
})();
