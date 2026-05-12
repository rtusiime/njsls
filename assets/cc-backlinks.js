/*
 * cc-backlinks.js
 * ----------------
 * Fetches Cohort Calendar live state from Supabase, builds a
 * standardCode → blocks index, and attaches "Taught in" sections
 * under each rendered standard entry on a subject page.
 *
 * Page contract:
 *   - Each rendered standard element has class `entry`, `std-entry`,
 *     or `pe-entry` and a `data-code` attribute whose value is the
 *     NJSLS standard code.
 *   - Page exposes `window.njslsOnRender` (optional). If present, we
 *     wrap it so backlinks re-attach after re-renders. Otherwise we
 *     just attach once on first DOMContentLoaded + corpus fetch.
 *
 * Code alignment notes:
 *   CC tags ~half of its blocks using current NJSLS 2023 codes
 *   (e.g., "5.NBT.B.7", "MS-LS1-7"). Others use older CCSS-style
 *   abbreviations (e.g., "SL.1", "5.MD.A.1") that don't exist in the
 *   current NJSLS corpus. We match by exact code only. Standards that
 *   never get a hit just don't render a "Taught in" section.
 */
(function () {
  const SUPABASE_URL = 'https://vaqdoeckaobmsalikmpx.supabase.co';
  const SUPABASE_KEY = 'sb_publishable_UlWZDjS5Yx07Cl-reOlLAg_qOsp7DLn';
  const DOC_ID = 'main';
  const CC_BASE_URL = 'https://john-forge.github.io/CohortCalendar/';

  const FETCH_TIMEOUT_MS = 8000;
  const COLLAPSE_THRESHOLD = 4; // Show first N blocks; rest behind "show all"

  // Day-of-week labels — CC stores d=0..4 as Mon..Fri
  const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  // Block type labels — readable rendering of the `tp` field
  const TYPE_LABELS = {
    'challenge':  'Challenge',
    'math':       'Math',
    'ela':        'ELA',
    'biology':    'Biology',
    'chem':       'Chemistry',
    'chem-lab':   'Chem lab',
    'cog-check':  'Cog check',
    'diagnostic': 'Diagnostic',
    'lunch':      'Lunch',
    'movement':   'Movement',
    'other':      'Other',
  };

  // Status: keep these on window so devs can poke at them in the console
  const state = window.__njslsCC = {
    status: 'idle',  // 'idle' | 'loading' | 'ready' | 'error'
    blocks: null,    // raw blocks array
    byCode: null,    // Map<code, blocks[]>
    totalTaggedBlocks: 0,
    uniqueCodesInCC: 0,
    matchedAgainstCorpus: null, // set externally if corpus available
    error: null,
  };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function fetchWithTimeout(url, opts, ms) {
    return new Promise((resolve, reject) => {
      const ctrl = new AbortController();
      const timer = setTimeout(() => { ctrl.abort(); reject(new Error('CC fetch timed out')); }, ms);
      fetch(url, Object.assign({}, opts, { signal: ctrl.signal }))
        .then(r => { clearTimeout(timer); resolve(r); })
        .catch(e => { clearTimeout(timer); reject(e); });
    });
  }

  async function loadCohortCalendar() {
    state.status = 'loading';
    try {
      const url = `${SUPABASE_URL}/rest/v1/documents?id=eq.${DOC_ID}&select=data`;
      const r = await fetchWithTimeout(url, {
        headers: {
          'apikey': SUPABASE_KEY,
          'Authorization': 'Bearer ' + SUPABASE_KEY,
        },
      }, FETCH_TIMEOUT_MS);
      if (!r.ok) throw new Error('Supabase HTTP ' + r.status);
      const rows = await r.json();
      if (!rows.length || !rows[0].data) throw new Error('Supabase returned no document');
      const blocks = rows[0].data.blocks || [];
      const byCode = new Map();
      let totalTagged = 0;
      for (const b of blocks) {
        const codes = b.std || [];
        if (!codes.length) continue;
        totalTagged++;
        for (const code of codes) {
          if (!byCode.has(code)) byCode.set(code, []);
          byCode.get(code).push(b);
        }
      }
      // Sort each list chronologically: by week, then day, then slot
      for (const list of byCode.values()) {
        list.sort((a, b) => (a.w - b.w) || (a.d - b.d) || ((a.s || 0) - (b.s || 0)));
      }
      state.blocks = blocks;
      state.byCode = byCode;
      state.totalTaggedBlocks = totalTagged;
      state.uniqueCodesInCC = byCode.size;
      state.status = 'ready';
      return state;
    } catch (err) {
      state.status = 'error';
      state.error = err.message || String(err);
      console.warn('[cc-backlinks] Could not load CC state:', state.error);
      return state;
    }
  }

  function blockChipHtml(block) {
    const type = TYPE_LABELS[block.tp] || block.tp || '';
    const week = (typeof block.w === 'number') ? ('W' + (block.w + 1)) : '';
    const day = (typeof block.d === 'number' && DAY_LABELS[block.d]) || '';
    const grades = (block.grades || []).join('/'); // "G5/G6" or "G7/G8"
    const dur = block.dur ? `${block.dur}m` : '';
    const title = (block.ttl || block.id || '').trim();
    const truncTitle = title.length > 38 ? title.slice(0, 37) + '…' : title;
    const href = CC_BASE_URL + '#' + encodeURIComponent(block.id);
    const meta = [week, day, grades, dur].filter(Boolean).join(' · ');

    return `<a class="cc-chip" href="${esc(href)}" target="_blank" rel="noopener" title="${esc(title)} (${esc(meta)})">
      <span class="cc-chip-type">${esc(type)}</span>
      <span class="cc-chip-meta">${esc(meta)}</span>
      <span class="cc-chip-title">${esc(truncTitle)}</span>
    </a>`;
  }

  function backlinksHtml(blocks) {
    const n = blocks.length;
    const collapsedCount = n > COLLAPSE_THRESHOLD ? n - COLLAPSE_THRESHOLD : 0;
    const visible = collapsedCount > 0 ? blocks.slice(0, COLLAPSE_THRESHOLD) : blocks;
    const hidden = collapsedCount > 0 ? blocks.slice(COLLAPSE_THRESHOLD) : [];

    const visibleChips = visible.map(blockChipHtml).join('');
    const hiddenChips = hidden.map(blockChipHtml).join('');

    return `
      <div class="cc-backlinks" data-expanded="false">
        <div class="cc-header">
          <span class="cc-header-label">Taught in</span>
          <span class="cc-header-count">${n} block${n === 1 ? '' : 's'} in Cohort Calendar</span>
        </div>
        <div class="cc-chips">
          ${visibleChips}
          ${hidden.length ? `<div class="cc-hidden-chips" hidden>${hiddenChips}</div>` : ''}
        </div>
        ${hidden.length ? `<button type="button" class="cc-expand-btn" aria-expanded="false">Show ${hidden.length} more</button>` : ''}
      </div>
    `;
  }

  function attachBacklinksToEntry(entry, byCode) {
    const code = entry.getAttribute('data-code');
    if (!code) return;
    if (entry.querySelector(':scope > .cc-backlinks')) return; // already attached
    const blocks = byCode.get(code);
    if (!blocks || !blocks.length) return;

    const wrap = document.createElement('div');
    wrap.innerHTML = backlinksHtml(blocks);
    const node = wrap.firstElementChild;
    entry.appendChild(node);

    // Wire expand button
    const expandBtn = node.querySelector('.cc-expand-btn');
    const hiddenWrap = node.querySelector('.cc-hidden-chips');
    if (expandBtn && hiddenWrap) {
      expandBtn.addEventListener('click', () => {
        const expanded = node.dataset.expanded === 'true';
        node.dataset.expanded = String(!expanded);
        hiddenWrap.hidden = expanded;
        expandBtn.setAttribute('aria-expanded', String(!expanded));
        expandBtn.textContent = expanded
          ? `Show ${hiddenWrap.children.length} more`
          : `Show fewer`;
      });
    }
  }

  function attachAll() {
    if (state.status !== 'ready') return 0;
    const entries = document.querySelectorAll('.entry[data-code], .std-entry[data-code], .pe-entry[data-code]');
    let n = 0;
    entries.forEach(e => {
      if (!e.querySelector(':scope > .cc-backlinks')) {
        const code = e.getAttribute('data-code');
        if (state.byCode.has(code)) {
          attachBacklinksToEntry(e, state.byCode);
          n++;
        }
      }
    });
    return n;
  }

  // Public API:
  //   window.attachCCBacklinks() — call after the page's render() runs
  //   Returns a Promise that resolves when CC state is loaded AND attached.
  window.attachCCBacklinks = async function attachCCBacklinks() {
    if (state.status === 'idle') await loadCohortCalendar();
    if (state.status === 'loading') {
      // wait for in-flight fetch
      while (state.status === 'loading') {
        await new Promise(r => setTimeout(r, 50));
      }
    }
    return attachAll();
  };

  // Auto-init: try to attach once on DOMContentLoaded. If the page renders
  // asynchronously (after a fetch), the page must call window.attachCCBacklinks()
  // itself once its render() completes.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { window.attachCCBacklinks(); });
  } else {
    window.attachCCBacklinks();
  }
})();
