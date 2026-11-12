(function () {
  const STROKE = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';

  const KIND_ICONS = {
    explain: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.6.45 1 1.15 1.1 1.9h5A2.5 2.5 0 0 1 15.6 13.8 6 6 0 0 0 12 3Z"/></svg>`,
    wrapup: `<svg viewBox="0 0 24 24" ${STROKE}><circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.5 2.5L16 9.5"/></svg>`,
    connector: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M9 3v4M15 3v4M6.5 7h11L16 12l1.5 5h-11L8 12 6.5 7Z"/><path d="M9 21v-4M15 21v-4"/></svg>`,
    csv_upload: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M12 15V4M8 8l4-4 4 4"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>`,
    sheet: `<svg viewBox="0 0 24 24" ${STROKE}><rect x="3.5" y="4" width="17" height="16" rx="1.5"/><path d="M3.5 10h17M3.5 15h17M9.5 4v16"/></svg>`,
    column_meaning: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M3 6h7M3 12h4M3 18h7"/><circle cx="18" cy="14" r="3.5"/><path d="M18 12.3v1.7l1.1.9"/></svg>`,
    analysis: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M4 20V10M11 20V4M18 20v-7"/><path d="M2.5 20h19"/></svg>`,
    categorize: `<svg viewBox="0 0 24 24" ${STROKE}><rect x="3" y="4" width="6" height="6" rx="1"/><rect x="15" y="4" width="6" height="6" rx="1"/><rect x="9" y="14" width="6" height="6" rx="1"/><path d="M6 10v2a2 2 0 0 0 2 2h1M18 10v2a2 2 0 0 0-2 2h-1"/></svg>`,
    career_select: `<svg viewBox="0 0 24 24" ${STROKE}><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18"/></svg>`,
    web_table: `<svg viewBox="0 0 24 24" ${STROKE}><rect x="3" y="4.5" width="18" height="15" rx="1.5"/><path d="M3 8.5h18M9 8.5v11"/></svg>`,
    group_share: `<svg viewBox="0 0 24 24" ${STROKE}><circle cx="8" cy="9" r="3"/><circle cx="17" cy="8" r="2.4"/><path d="M3 19c0-3 2.3-5 5-5s5 2 5 5M14.5 19c.2-2.2 1.7-3.9 3.7-4.1 1.9.2 3.3 1.6 3.8 3.6"/></svg>`,
    inquiry_check: `<svg viewBox="0 0 24 24" ${STROKE}><rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="m8 9 1.5 1.5L12 8M8 15l1.5 1.5L12 14M14 9.5h3M14 15.5h3"/></svg>`,
    flexible_analysis: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M4 6h10M4 12h16M4 18h7"/><circle cx="17" cy="6" r="2"/><circle cx="9" cy="18" r="2"/></svg>`,
    presentation: `<svg viewBox="0 0 24 24" ${STROKE}><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/></svg>`,
    discuss: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M4 5.5h13a2 2 0 0 1 2 2V14a2 2 0 0 1-2 2H10l-4.5 4V16H4a2 2 0 0 1-2-2V7.5a2 2 0 0 1 2-2Z"/><path d="M7 9.5h9M7 12.5h6"/></svg>`,
    evidence: `<svg viewBox="0 0 24 24" ${STROKE}><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.3 15.3 5.2 5.2M8 10.5h5M10.5 8v5"/></svg>`,
    column_guess: `<svg viewBox="0 0 24 24" ${STROKE}><rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9h18"/><path d="M10.1 13.4a2 2 0 1 1 2.5 2c-.4.2-.6.5-.6.9v.3M12 18.9h.01"/></svg>`,
  };

  const BOOK_ICON = `<svg viewBox="0 0 24 24" ${STROKE}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H12v18H6.5A2.5 2.5 0 0 0 4 23Z"/><path d="M12 3h5.5A2.5 2.5 0 0 1 20 5.5V21a2.5 2.5 0 0 0-2.5-2.5H12"/></svg>`;

  const ID_ICON_OVERRIDES = {
    gg_library: BOOK_ICON,
    gg_library_fetch: BOOK_ICON,
    benford_data: BOOK_ICON,
    neis_meal: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M6 3v7a2 2 0 0 0 2 2v9M6 3v5M9 3v5M6 8h3"/><path d="M16 3c-1.5 0-3 1.8-3 5s1.2 4.5 2 5v8M18 3v18"/></svg>`,
    boxplot: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M4 12h4M20 12h-4M8 7h8v10H8Z M12 7V4M12 17v3"/></svg>`,
    frequency_polygon: `<svg viewBox="0 0 24 24" ${STROKE}><path d="M2.5 20h19"/><path d="M4 17 8 9l4 4 4-8 4 5"/></svg>`,
  };

  function resolveIcon(step) {
    if (!step) return "";
    return ID_ICON_OVERRIDES[step.id] || KIND_ICONS[step.kind] || "";
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.getStepIcon = resolveIcon;
})();
