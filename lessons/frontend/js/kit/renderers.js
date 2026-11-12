(function () {
  function requireKit(name) {
    const fn = window.LessonKit[name];
    if (typeof fn !== "function") {
      throw new Error(`이 화면에 ${name}이(가) 로드되지 않았습니다.`);
    }
    return fn;
  }

  const RENDERERS = {
    explain: async (body, card) => window.LessonKit.renderExplain(body, card),
    wrapup: async (body, card) => window.LessonKit.renderExplain(body, card),
    discuss: async (body, card) => window.LessonKit.renderExplain(body, card),
    sheet: async (body, card, ctx) => {
      window.LessonKit.renderExplain(body, card);
      const sheetContainer = document.createElement("div");
      body.appendChild(sheetContainer);
      await requireKit("renderSheet")(sheetContainer, ctx.datasetId, {
        limit: card.sheet_limit || 60,
        columns: card.sheet_columns,
      });
    },
    column_meaning: async (body, card, ctx) => requireKit("renderColumnMeaningAsk")(body, card, ctx),
    diag: async (body, card, ctx) => requireKit("renderDiagItem")(body, card, ctx),
    evidence: async (body, card, ctx) => requireKit("renderEvidence")(body, card, ctx),
    column_guess: async (body, card, ctx) => requireKit("renderEvidence")(body, card, ctx),
    analysis: async (body, card, ctx) => requireKit("renderAnalysisStep")(body, card, ctx),
    connector: async (body, card, ctx) => requireKit("renderConnector")(body, card, ctx),
    csv_upload: async (body, card, ctx) => requireKit("renderCsvUpload")(body, card, ctx),
    categorize: async (body, card, ctx) => requireKit("renderCategorize")(body, card, ctx),
    career_select: async (body, card, ctx) => requireKit("renderCareerSelect")(body, card, ctx),
    web_table: async (body, card, ctx) => requireKit("renderWebTableInput")(body, card, ctx),
    group_share: async (body, card, ctx) => requireKit("renderGroupShare")(body, card, ctx),
    inquiry_check: async (body, card, ctx) => requireKit("renderInquiryCheck")(body, card, ctx),
    flexible_analysis: async (body, card, ctx) => requireKit("renderFlexibleAnalysis")(body, card, ctx),
    presentation: async (body, card, ctx) => requireKit("renderPresentation")(body, card, ctx),
  };

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.RENDERERS = RENDERERS;
})();
