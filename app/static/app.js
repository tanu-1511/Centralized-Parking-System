/* Small progressive enhancements. Every page still works without this file. */
(function () {
  'use strict';

  // Live regions: <div data-live="5"> fetches this page every 5 seconds and
  // swaps in the matching region. Text typed outside the region is kept.
  function startLiveRegions() {
    document.querySelectorAll('[data-live]').forEach(function (region, index) {
      var seconds = parseInt(region.getAttribute('data-live'), 10) || 5;
      setInterval(function () {
        if (document.hidden) return;
        fetch(window.location.href, { credentials: 'same-origin', cache: 'no-store' })
          .then(function (response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.text();
          })
          .then(function (html) {
            var fresh = new DOMParser().parseFromString(html, 'text/html')
              .querySelectorAll('[data-live]')[index];
            if (fresh) {
              region.innerHTML = fresh.innerHTML;
              applyAllFilters();
            }
          })
          .catch(function () { /* keep the last good view */ });
      }, seconds * 1000);
    });
  }

  // Search box above a table: hides rows that do not contain the text.
  function applyFilter(input) {
    var table = document.getElementById(input.getAttribute('data-filter-for'));
    if (!table) return;
    var query = input.value.trim().toLowerCase();
    Array.prototype.forEach.call(table.rows, function (row) {
      if (row.querySelector('th')) return; // keep the header row
      row.hidden = query !== '' && row.textContent.toLowerCase().indexOf(query) === -1;
    });
  }

  function applyAllFilters() {
    document.querySelectorAll('[data-filter-for]').forEach(applyFilter);
  }

  // Click a column header in a .sortable table to sort by it (click again to reverse).
  function sortTable(th) {
    var table = th.closest('table');
    var column = th.cellIndex;
    var ascending = th.getAttribute('data-dir') !== 'asc';
    var header = table.rows[0];
    Array.prototype.forEach.call(header.cells, function (cell) { cell.removeAttribute('data-dir'); });
    th.setAttribute('data-dir', ascending ? 'asc' : 'desc');

    var rows = Array.prototype.slice.call(table.rows, 1);
    rows.sort(function (a, b) {
      var x = a.cells[column] ? a.cells[column].textContent.trim() : '';
      var y = b.cells[column] ? b.cells[column].textContent.trim() : '';
      var result = /^-?[\d.]+$/.test(x) && /^-?[\d.]+$/.test(y)
        ? parseFloat(x) - parseFloat(y)
        : x.localeCompare(y, undefined, { numeric: true });
      return ascending ? result : -result;
    });
    rows.forEach(function (row) { header.parentNode.appendChild(row); });
  }

  // Map: show the clicked slot's details in the panel above the map.
  function showSlot(el) {
    var panel = document.getElementById('slot-info');
    if (!panel) return;
    var parts = ['Slot ' + el.getAttribute('data-slot'),
                 'floor ' + el.getAttribute('data-floor'),
                 el.getAttribute('data-state')];
    if (el.getAttribute('data-ev') === '1') parts.push('EV charging');
    if (el.getAttribute('data-accessible') === '1') parts.push('accessible');
    panel.textContent = parts.join(' · ');
  }

  // Booking: fill in the end time and show the duration; block out-of-range bookings.
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function toInputValue(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function setupBooking() {
    var start = document.getElementById('start_time');
    var end = document.getElementById('end_time');
    var hint = document.getElementById('duration-hint');
    if (!start || !end || !hint) return;

    function update() {
      hint.classList.remove('error');
      if (!start.value || !end.value) {
        hint.textContent = 'Pick a start and end time.';
        return;
      }
      var minutes = Math.round((new Date(end.value) - new Date(start.value)) / 60000);
      if (isNaN(minutes)) {
        hint.textContent = 'Pick a start and end time.';
      } else if (minutes < 30) {
        hint.textContent = 'Too short: a booking must be at least 30 minutes.';
        hint.classList.add('error');
      } else if (minutes > 720) {
        hint.textContent = 'Too long: a booking can be at most 12 hours.';
        hint.classList.add('error');
      } else {
        hint.textContent = 'Duration: ' + Math.floor(minutes / 60) + ' h ' + (minutes % 60) + ' min';
      }
    }

    start.addEventListener('change', function () {
      if (start.value) {
        var s = new Date(start.value);
        var e = end.value ? new Date(end.value) : null;
        if (!e || e <= s) {
          end.value = toInputValue(new Date(s.getTime() + 60 * 60000));
        }
      }
      update();
    });
    end.addEventListener('change', update);
    start.addEventListener('input', update);
    end.addEventListener('input', update);
    update();
  }

  // Delegated handlers, so they keep working after a live region is swapped.
  document.addEventListener('input', function (e) {
    if (e.target.hasAttribute && e.target.hasAttribute('data-filter-for')) applyFilter(e.target);
  });

  document.addEventListener('change', function (e) {
    var form = e.target.form;
    if (form && form.hasAttribute('data-autosubmit')) {
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    }
  });

  document.addEventListener('click', function (e) {
    var th = e.target.closest ? e.target.closest('table.sortable th') : null;
    if (th) { sortTable(th); return; }
    var slot = e.target.closest ? e.target.closest('.slot[data-slot]') : null;
    if (slot) showSlot(slot);
  });

  document.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('.slot[data-slot]')) {
      e.preventDefault();
      showSlot(e.target);
    }
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    var message = form.getAttribute('data-confirm');
    if (message && !window.confirm(message)) { e.preventDefault(); return; }
    var hint = document.getElementById('duration-hint');
    if (form.id === 'booking-form' && hint && hint.classList.contains('error')) {
      e.preventDefault();
      hint.scrollIntoView({ block: 'center' });
      return;
    }
    Array.prototype.forEach.call(form.querySelectorAll('button[type="submit"]'), function (b) {
      b.disabled = true;
    });
  });

  document.addEventListener('DOMContentLoaded', function () {
    setupBooking();
    applyAllFilters();
    startLiveRegions();
  });
})();
