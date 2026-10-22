"""Fixed offline report controls. Captured/user text is never interpolated here."""

REPORT_SCRIPT = r'''(() => {
  'use strict';
  const controls = document.getElementById('review-controls');
  const query = document.getElementById('find-text');
  const matchCase = document.getElementById('find-case');
  const status = document.getElementById('find-status');
  const changeStatus = document.getElementById('change-status');
  const cells = Array.from(document.querySelectorAll('.saved-text')).map(node => {
    const base = node.cloneNode(true);
    base.querySelectorAll('.match, .active').forEach(span => span.classList.remove('match', 'active'));
    return {node, base, text: node.textContent};
  });
  const changes = Array.from(document.querySelectorAll('[data-change]'));
  const sections = Array.from(document.querySelectorAll('.viewport details'));
  const sectionStatus = document.getElementById('section-status');
  const expandAll = document.getElementById('expand-all');
  const collapseAll = document.getElementById('collapse-all');
  let hits = [], hitIndex = -1, changeIndex = -1, timer = null, limited = false;
  const previousMatch = document.getElementById('previous-match');
  const nextMatch = document.getElementById('next-match');
  const previousChange = document.getElementById('previous-change');
  const nextChange = document.getElementById('next-change');
  function reveal(node) {
    for (let parent = node.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    node.scrollIntoView({block: 'center', inline: 'nearest'});
  }
  function updateSections() {
    sectionStatus.textContent = sections.length ? `${sections.filter(section => section.open).length} of ${sections.length} sections expanded` : 'No collapsed context sections';
  }
  sections.forEach(section => section.addEventListener('toggle', updateSections));
  expandAll.disabled = collapseAll.disabled = !sections.length;
  expandAll.addEventListener('click', () => { sections.forEach(section => { section.open = true; }); updateSections(); });
  collapseAll.addEventListener('click', () => { sections.forEach(section => { section.open = false; }); updateSections(); });
  updateSections();
  function selectHit(index, scroll = true) {
    if (!hits.length) return;
    if (hitIndex >= 0) hits[hitIndex].marks.forEach(mark => mark.classList.remove('live-current'));
    hitIndex = (index + hits.length) % hits.length;
    const hit = hits[hitIndex];
    hit.marks.forEach(mark => mark.classList.add('live-current'));
    if (scroll) reveal(hit.marks[0]);
    status.textContent = `Match ${hitIndex + 1} of ${hits.length}${limited ? '+' : ''} · ${hit.side} line ${hit.line}${limited ? ' · limit reached; refine search' : ''}`;
  }
  function search(initialIndex = 0, scroll = true) {
    if (timer !== null) { clearTimeout(timer); timer = null; }
    hits = []; hitIndex = -1; limited = false;
    cells.forEach(cell => cell.node.replaceChildren(...Array.from(cell.base.childNodes, child => child.cloneNode(true))));
    const value = query.value;
    const pattern = value ? new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), matchCase.checked ? 'gu' : 'giu') : null;
    for (const cell of cells) {
      if (!pattern || limited) break;
      pattern.lastIndex = 0;
      const ranges = [];
      let found;
      while ((found = pattern.exec(cell.text)) !== null) {
        if (hits.length === 10000) { limited = true; break; }
        const hit = {marks: [], side: cell.node.dataset.side, line: cell.node.dataset.line};
        hits.push(hit);
        ranges.push({start: found.index, end: found.index + found[0].length, hit});
      }
      if (!ranges.length) continue;
      const walker = document.createTreeWalker(cell.node, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      let offset = 0, rangeIndex = 0;
      for (const node of nodes) {
        const text = node.nodeValue, end = offset + text.length;
        while (rangeIndex < ranges.length && ranges[rangeIndex].end <= offset) rangeIndex++;
        let index = rangeIndex, cursor = 0;
        const fragment = document.createDocumentFragment();
        while (index < ranges.length && ranges[index].start < end) {
          const range = ranges[index];
          const start = Math.max(0, range.start - offset), stop = Math.min(text.length, range.end - offset);
          fragment.appendChild(document.createTextNode(text.slice(cursor, start)));
          const mark = document.createElement('mark');
          mark.className = 'live-hit'; mark.textContent = text.slice(start, stop);
          fragment.appendChild(mark); range.hit.marks.push(mark); cursor = stop; index++;
        }
        if (cursor) {
          fragment.appendChild(document.createTextNode(text.slice(cursor)));
          node.replaceWith(fragment);
        }
        offset = end;
      }
    }
    previousMatch.disabled = nextMatch.disabled = !hits.length;
    status.textContent = value ? 'No matches in saved text' : 'Search both snapshots · Ctrl+F · F3 / Shift+F3';
    if (hits.length) selectHit(Math.min(initialIndex, hits.length - 1), scroll);
  }
  function moveMatch(direction) {
    if (timer !== null) { search(direction < 0 ? 9999 : 0); return; }
    selectHit(hitIndex + direction);
  }
  function moveChange(direction) {
    if (!changes.length) return;
    if (changeIndex >= 0) changes[changeIndex].classList.remove('review-current');
    changeIndex = changeIndex < 0 ? (direction > 0 ? 0 : changes.length - 1) : (changeIndex + direction + changes.length) % changes.length;
    const row = changes[changeIndex]; row.classList.add('review-current'); reveal(row);
    changeStatus.textContent = `Change ${changeIndex + 1} of ${changes.length}`;
  }
  query.addEventListener('input', () => {
    if (timer !== null) clearTimeout(timer);
    previousMatch.disabled = nextMatch.disabled = true;
    status.textContent = 'Searching…'; timer = setTimeout(() => search(), 180);
  });
  matchCase.addEventListener('change', () => search());
  previousMatch.addEventListener('click', () => moveMatch(-1));
  nextMatch.addEventListener('click', () => moveMatch(1));
  previousChange.addEventListener('click', () => moveChange(-1));
  nextChange.addEventListener('click', () => moveChange(1));
  document.getElementById('clear-find').addEventListener('click', () => { query.value = ''; search(); query.focus(); });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
      event.preventDefault(); query.focus(); query.select();
    } else if (event.key === 'F3' || (event.target === query && event.key === 'Enter')) {
      event.preventDefault(); moveMatch(event.shiftKey ? -1 : 1);
    } else if (event.key === 'F7') {
      event.preventDefault(); moveChange(event.shiftKey ? -1 : 1);
    } else if (event.target === query && event.key === 'Escape') {
      event.preventDefault(); query.value = ''; search();
    }
  });
  previousChange.disabled = nextChange.disabled = !changes.length;
  changeStatus.textContent = `${changes.length} change(s)`;
  controls.hidden = false;
  search(Number(controls.dataset.initialMatch), false);
})();'''
