(function () {
  "use strict";

  const DATA = window.AGENT_DATA;
  const R = window.DemoResults;
  const esc = R.esc;
  const STORE_KEY = "stat-agent-demo-agent";
  const STEPS = ["주제", "자료", "분석", "보고서", "피드백"];
  const LEVEL = { middle: "중학교", high: "고등학교" };
  const CAUSAL = ["때문에", "때문이", "원인은", "원인이", "탓에", "덕분에", "영향을 준", "영향을 미친"];
  const OVERREACH = ["항상", "무조건", "절대", "모든 사람", "누구나", "반드시"];
  const SCEN_TIPS = {
    private_education_cost: {
      intro: "17개 시도의 사교육비와 참여율 자료입니다. 지도로 지역 차이를 보고, 참여율과 사교육비가 함께 움직이는지 확인해 보세요.",
      insight: { compute_correlation: "참여율과 사교육비의 상관계수가 0.9를 넘습니다. 다만 이 값은 시도 평균끼리의 관계라, 학생 한 명 한 명에게 그대로 옮길 수는 없습니다.", plot_scatter: "산점도에서 다른 시도들과 멀리 떨어진 점이 있는지 찾아보세요. 상관계수 하나로는 보이지 않는 지역입니다." },
    },
    summer_temperature: {
      intro: "서울의 25년 여름 기온 자료입니다. 선그래프로 흐름을 보고, 앞 시기와 뒤 시기를 상자그림으로 나란히 비교해 보세요.",
      insight: { plot_line: "해마다 오르내림이 큽니다. 한두 해만 보고 '더워졌다'고 말하기보다 여러 해의 흐름과 시기별 분포를 함께 봅니다.", plot_boxplot: "두 시기의 중앙값과 상자의 위치를 비교하세요. 상자가 겹치는 정도도 함께 봅니다." },
    },
    school_traffic_safety: {
      intro: "세종시 학교 80곳의 교통안전시설과 사고위험밀도 자료입니다. 전체 상관계수와 생활권별 상관계수를 견주어 보세요.",
      insight: { compute_grouped_correlation: "전체로는 관계가 거의 없어 보여도, 생활권으로 나누면 양의 관계인 곳과 음의 관계인 곳이 갈립니다. 나눠 보지 않으면 놓치는 모습입니다.", compute_correlation: "전체 자료의 상관계수입니다. 생활권별 상관계수와 견주어 보면 다른 모습이 보입니다." },
    },
  };

  let S = load() || fresh();
  let focused = null;

  function fresh() {
    return { scen: null, step: 0, guideOn: true, collapsed: false, adviceOpen: false, input: "", decided: "", started: false, dataOk: false, opened: [], hints: {}, interp: {}, saved: {}, feedback: {}, conclusion: "", reportSaved: false, reflect: {}, reflectSaved: false };
  }
  function load() {
    try {
      const raw = sessionStorage.getItem(STORE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }
  function save() {
    try {
      sessionStorage.setItem(STORE_KEY, JSON.stringify(S));
    } catch (e) {
      return;
    }
  }
  const $ = (sel, root = document) => root.querySelector(sel);
  function scen() {
    return DATA.scenarios[S.scen];
  }
  function savedList() {
    return scen().analyses.map((a, i) => [a, i]).filter(([, i]) => S.saved[i]);
  }

  function feedbackFor(a, text) {
    text = (text || "").trim();
    const strengths = [];
    const improvements = [];
    const questions = ["이 해석에서 자료로 확인한 사실과 내 추측은 어떻게 구분되나요?", "탐구 질문에 답하려면 어떤 내용을 더 적어야 할까요?"];
    if (/\d/.test(text)) strengths.push("분석 결과의 수치를 인용해서 근거가 분명합니다.");
    else improvements.push("그래프나 표에서 읽은 값을 한 개라도 적어 보세요. 숫자가 있으면 근거가 분명해집니다.");
    const sentences = text.split(/[.!?\n]+/).filter((x) => x.trim()).length;
    if (sentences >= 2) strengths.push("한 문장으로 끝내지 않고 관찰한 내용을 나누어 적었습니다.");
    else improvements.push("관찰한 사실 한 문장, 그것이 탐구 질문에 어떤 뜻인지 한 문장으로 나누어 적어 보세요.");
    if (CAUSAL.some((m) => text.includes(m))) {
      improvements.push("원인을 단정하는 표현이 있습니다. 이 자료로 확인한 것은 함께 나타나는 관계이므로 '~때문이다' 대신 '~와 함께 나타난다'처럼 적어 보세요.");
      questions.unshift("이 자료만으로 원인을 말할 수 있나요, 아니면 관계만 말할 수 있나요?");
    }
    if (OVERREACH.some((m) => text.includes(m))) improvements.push("'항상', '모든'처럼 자료 범위를 넘는 표현이 있습니다. 자료가 다루는 기간과 대상 안에서만 말해 주세요.");
    if ((a.args || {}).group_by) questions.push("두 집단의 차이는 대표값 차이인가요, 퍼진 정도의 차이인가요?");
    if (["compute_correlation", "compute_grouped_correlation", "plot_scatter"].includes(a.tool)) questions.push("관계의 방향(같이 커지는지, 반대로 가는지)을 해석에 적었나요?");
    if (!strengths.length) strengths.push("결과를 직접 읽고 자기 문장으로 옮기려는 시도가 보입니다.");
    if (!improvements.length) improvements.push("자료가 답해 주지 못하는 부분이 무엇인지 한 문장 덧붙이면 더 좋아집니다.");
    return { strengths: strengths.slice(0, 3), improvements: improvements.slice(0, 3), questions: questions.slice(0, 3) };
  }

  function stepTopic(s) {
    const adv = s.advice;
    let html = `<div class="card"><p class="group">${esc(LEVEL[s.level])} 탐구</p><h2>${esc(s.title)}</h2><p>${esc(s.question)}</p>`;
    html += `<div class="prompt"><div class="q">궁금한 것을 한두 문장으로 적어 보세요</div><textarea id="a-input">${esc(S.input || s.student_input)}</textarea><p class="muted">체험판은 이 예시 입력에 대한 조언을 미리 받아 두었습니다.</p>`;
    html += S.adviceOpen ? "" : `<div class="row"><button type="button" class="primary" id="a-advice">직접 자료 조사 탐구 조언받기</button></div>`;
    html += `</div>`;
    if (S.adviceOpen) {
      html += `<div class="reveal"><b>AI 조언</b><p>${esc(adv.overall_advice)}</p><b>탐구 방향 후보</b>`;
      html += (adv.candidate_questions || [])
        .slice(0, 4)
        .map(
          (q) =>
            `<div class="cand"><b>${esc(q.title)}</b><p class="muted">추천 분석: ${esc((q.recommended_analysis || []).join(", "))}</p>${(q.cautions || []).length ? `<p class="muted">주의: ${esc(q.cautions.join(", "))}</p>` : ""}${q.good_choice_when ? `<p class="muted">${esc(q.good_choice_when)}</p>` : ""}</div>`,
        )
        .join("");
      if ((adv.refinement_tips || []).length) html += `<b>질문을 다듬는 방법</b><ul>${adv.refinement_tips.slice(0, 3).map((t) => `<li>${esc(typeof t === "string" ? t : t.tip || JSON.stringify(t))}</li>`).join("")}</ul>`;
      html += `<p class="muted">체험판의 조언은 생성형 AI 대신 앱에 들어 있는 규칙 기반 안내입니다. 실제 수업에서는 AI가 입력에 맞춰 구체적인 질문 후보를 제안합니다.</p></div>`;
      html += `<div class="prompt"><div class="q">결정한 탐구 질문</div><p class="muted">예시 주제의 질문이 들어 있습니다. 조언을 보고 고쳐 써도 됩니다.</p><textarea id="a-decided">${esc(S.decided || s.question)}</textarea><div class="row"><button type="button" class="primary" id="a-start">이 주제로 자료 단계 시작</button></div></div>`;
    }
    return html + `</div>`;
  }

  function stepData(s) {
    const d = s.dataset;
    let html = `<div class="card"><p class="group">자료</p><h2>${esc(d.name)}</h2><p>${esc(d.description || "")}</p>`;
    html += `<div class="reveal"><b>출처</b><p>${esc(d.source || "")}</p><p class="muted">${esc(d.source_note || "")}</p>${(d.schema.source_notes || [])
      .map((n) => `<p class="muted"><b>${esc(n.label)}</b> ${esc(n.text)}</p>`)
      .join("")}</div>`;
    html += `<h3>자료 표 (${d.table.total}행)</h3><div class="sheet-inline">${R.table(d.table.columns, d.table.rows.slice(0, 30))}</div>`;
    html += `<h3>항목 카드</h3><div class="col-cards">${(d.schema.columns || [])
      .map(
        (c) =>
          `<div class="col-card"><b>${esc(c.display_name || c.name)}</b> <span class="tag">${esc(c.role_label || c.dtype || "")}</span><p>${esc(c.description || "")}${c.unit ? ` (단위: ${esc(c.unit)})` : ""}</p>${(c.warnings || []).map((w) => `<p class="muted">${esc(typeof w === "string" ? w : w.message || "")}</p>`).join("")}</div>`,
      )
      .join("")}</div>`;
    html += S.dataOk ? `<div class="row"><span class="sent">✓ 이 자료로 분석합니다</span></div>` : `<div class="row"><button type="button" class="primary" id="a-data">이 자료로 분석하기</button></div>`;
    return html + `</div>`;
  }

  function stepAnalysis(s) {
    let html = `<div class="card"><p class="group">분석</p><h2>${esc(S.decided || s.question)}</h2><p>추천 분석을 눌러 실행합니다. 결과 카드가 생기면 그 자리에서 해석을 씁니다.</p><div class="career-fields">${s.analyses
      .map((a, i) => `<button type="button" data-run="${i}" class="${S.opened.includes(i) ? "primary" : ""}" title="${esc(a.description || "")}">${esc(a.label)}</button>`)
      .join("")}</div></div>`;
    S.opened
      .slice()
      .reverse()
      .forEach((i) => {
        const a = s.analyses[i];
        const fb = S.feedback[i];
        html += `<div class="card result-card" id="res-${i}"><p class="group">분석 결과</p><h2>${esc(a.label)}</h2><p class="muted">${esc(a.description || "")}</p><div class="reveal">${R.render(a)}</div>`;
        const ins = (SCEN_TIPS[s.topic_id] || {}).insight || {};
        if (S.hints[i]) {
          const h = a.hints || {};
          html += `<div class="hint"><b>관찰점과 유도 질문</b><ul>${(h.observations || []).slice(0, 3).concat((h.questions || []).slice(0, 2)).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
        } else {
          html += `<div class="row"><button type="button" data-hint="${i}">관찰점, 유도 질문 불러오기</button><span class="muted">무엇을 볼지 막막하면 먼저 눌러 보세요.</span></div>`;
        }
        html += `<div class="prompt"><div class="q">이 결과에 대한 내 해석</div><textarea data-interp="${i}" placeholder="관찰한 사실과 근거 수치, 이 결과로 말할 수 있는 범위를 적어 보세요.">${esc(S.interp[i] || "")}</textarea>`;
        html += `<div class="row"><button type="button" data-fb="${i}">AI 피드백 받기</button><button type="button" class="primary" data-save="${i}">해석 저장</button>${S.saved[i] ? '<span class="sent">✓ 해석을 저장했습니다</span>' : ""}<span class="error" id="err-${i}"></span></div>`;
        if (fb) {
          html += `<div class="hint"><b>잘한 점</b><ul>${fb.strengths.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><b>보완할 점</b><ul>${fb.improvements.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><b>다시 생각해 볼 질문</b><ul>${fb.questions
            .map((x) => `<li>${esc(x)}</li>`)
            .join("")}</ul><p class="muted">이 피드백은 해석을 대신 써 주지 않습니다. 체험판은 앱의 규칙 기반 피드백을 씁니다.</p></div>`;
        }
        if (ins[a.tool] && S.hints[i]) html += `<p class="muted"><b>체험 도움말</b> ${esc(ins[a.tool])}</p>`;
        html += `</div></div>`;
      });
    return html;
  }

  function stepReport(s) {
    const items = savedList();
    let html = `<div class="card"><p class="group">보고서</p><h2>탐구 보고서 구성</h2><p>저장한 해석이 결과 카드와 함께 A4 포스터에 실립니다. 결론을 쓰고 저장하세요. 실제 앱에서는 카드를 끌어 자리와 크기를 바꾸고 PDF나 PPTX로 내려받습니다.</p>`;
    html += `<div class="row"><button type="button" id="a-draft">저장한 해석을 이어 붙여 결론 초안 넣기</button><button type="button" id="a-print">인쇄 또는 PDF로 저장</button></div></div>`;
    html += `<div class="poster" id="poster"><p class="poster-eyebrow">통계 탐구 포스터</p><h1>${esc(S.decided || s.question)}</h1><div class="poster-grid">`;
    html += `<section><h3>탐구 질문</h3><p>${esc(S.decided || s.question)}</p></section><section><h3>사용한 자료와 출처</h3><p><b>${esc(s.dataset.name)}</b></p><p class="muted">${esc(s.dataset.source || "")}</p></section>`;
    items.forEach(([a, i]) => {
      html += `<section class="wide"><h3>${esc(a.label)}</h3>${R.render(a)}<p>${esc(S.interp[i] || "")}</p></section>`;
    });
    html += `<section class="wide"><h3>결론</h3><textarea id="a-conclusion" placeholder="탐구 질문에 대한 답과, 이 자료로 말할 수 없는 것을 함께 씁니다.">${esc(S.conclusion)}</textarea></section></div></div>`;
    html += `<div class="card"><div class="row"><button type="button" class="primary" id="a-report">보고서 저장</button>${S.reportSaved ? '<span class="sent">✓ 저장했습니다</span>' : ""}<span class="error" id="err-report"></span></div></div>`;
    return html;
  }

  function stepFeedback() {
    const qs = ["이번 탐구에서 가장 어려웠던 점은?", "데이터로 확인한 것과 예상이 달랐던 점은?", "다음에 더 알아보고 싶은 것은?"];
    let html = `<div class="card"><p class="group">피드백</p><h2>피드백</h2><p class="muted">실제 앱에서는 교사가 보고서에 남긴 피드백이 여기에 나타납니다. 체험판에는 교사가 없습니다.</p><h3>자기 성찰 (선택)</h3>`;
    qs.forEach((q, i) => (html += `<div class="prompt"><div class="q">${esc(q)}</div><textarea data-reflect="${i}">${esc(S.reflect[i] || "")}</textarea></div>`));
    html += `<div class="row"><button type="button" class="primary" id="a-reflect">성찰 저장</button>${S.reflectSaved ? '<span class="sent">✓ 저장했습니다</span>' : ""}<button type="button" id="a-other">다른 시나리오 체험하기</button></div></div>`;
    return html;
  }

  function stepAllowed(i) {
    if (i <= 0) return true;
    if (i === 1) return S.started;
    if (i === 2) return S.dataOk;
    if (i === 3) return savedList().length > 0;
    if (i === 4) return S.reportSaved;
    return false;
  }

  function render() {
    const s = scen();
    $("#scen-label").textContent = `${s.title} (${LEVEL[s.level]})`;
    $("#steps").innerHTML = STEPS.map((name, i) => `<button type="button" data-step="${i}" class="${i === S.step ? "current" : ""}" ${stepAllowed(i) ? "" : "disabled"}><span>${i + 1}</span> ${name}</button>`).join("");
    const body = [stepTopic, stepData, stepAnalysis, stepReport, stepFeedback][S.step](s);
    $("#stage").innerHTML = body;
    $("#prev").disabled = S.step === 0;
    $("#next").disabled = S.step === 4 || !stepAllowed(S.step + 1);
    bind();
    save();
    renderGuide();
  }

  function go(step) {
    if (!stepAllowed(step)) return;
    S.step = step;
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function bind() {
    const s = scen();
    document.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => go(Number(b.dataset.step))));
    const inp = $("#a-input");
    if (inp) inp.addEventListener("input", () => { S.input = inp.value; save(); });
    const adv = $("#a-advice");
    if (adv) adv.addEventListener("click", () => { S.adviceOpen = true; render(); });
    const dec = $("#a-decided");
    if (dec) dec.addEventListener("input", () => { S.decided = dec.value; save(); renderGuide(); });
    const st = $("#a-start");
    if (st) st.addEventListener("click", () => { S.decided = ($("#a-decided").value || s.question).trim(); S.started = true; go(1); });
    const dt = $("#a-data");
    if (dt) dt.addEventListener("click", () => { S.dataOk = true; go(2); });
    document.querySelectorAll("[data-run]").forEach((b) => b.addEventListener("click", () => {
      const i = Number(b.dataset.run);
      if (!S.opened.includes(i)) S.opened.push(i);
      render();
      const el = document.getElementById(`res-${i}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
    document.querySelectorAll("[data-hint]").forEach((b) => b.addEventListener("click", () => { S.hints[Number(b.dataset.hint)] = true; render(); }));
    document.querySelectorAll("[data-interp]").forEach((t) => t.addEventListener("input", () => { S.interp[Number(t.dataset.interp)] = t.value; save(); renderGuide(); }));
    document.querySelectorAll("[data-fb]").forEach((b) => b.addEventListener("click", () => {
      const i = Number(b.dataset.fb);
      if (!(S.interp[i] || "").trim()) { $(`#err-${i}`).textContent = "해석을 먼저 적어 주세요."; return; }
      S.feedback[i] = feedbackFor(s.analyses[i], S.interp[i]);
      render();
    }));
    document.querySelectorAll("[data-save]").forEach((b) => b.addEventListener("click", () => {
      const i = Number(b.dataset.save);
      if (!(S.interp[i] || "").trim()) { $(`#err-${i}`).textContent = "해석을 먼저 적어 주세요."; return; }
      S.saved[i] = true;
      render();
    }));
    const dr = $("#a-draft");
    if (dr) dr.addEventListener("click", () => { S.conclusion = savedList().map(([, i]) => S.interp[i]).join(" "); render(); });
    const pr = $("#a-print");
    if (pr) pr.addEventListener("click", () => window.print());
    const con = $("#a-conclusion");
    if (con) con.addEventListener("input", () => { S.conclusion = con.value; save(); renderGuide(); });
    const rp = $("#a-report");
    if (rp) rp.addEventListener("click", () => {
      if (!S.conclusion.trim()) { $("#err-report").textContent = "결론을 적어 주세요."; return; }
      S.reportSaved = true;
      render();
    });
    document.querySelectorAll("[data-reflect]").forEach((t) => t.addEventListener("input", () => { S.reflect[Number(t.dataset.reflect)] = t.value; save(); }));
    const rf = $("#a-reflect");
    if (rf) rf.addEventListener("click", () => { S.reflectSaved = true; render(); });
    const ot = $("#a-other");
    if (ot) ot.addEventListener("click", () => welcome());
  }

  function milestones() {
    return [
      ["주제 확정", S.started],
      ["자료 준비", S.dataOk],
      ["분석 실행", S.opened.length > 0],
      ["해석 저장", savedList().length > 0],
      ["보고서", S.reportSaved],
      ["피드백", S.step === 4],
    ];
  }

  function guideTask() {
    const s = scen();
    const tip = SCEN_TIPS[s.topic_id] || {};
    if (S.step === 0) {
      if (!S.adviceOpen) return { title: "궁금한 것 적고 조언받기", message: "입력 칸에 궁금한 점을 적고 '직접 자료 조사 탐구 조언받기'를 누릅니다. 예시 입력이 미리 들어 있습니다.", target: "#a-advice" };
      return { title: "탐구 질문 정하기", message: "AI 조언을 읽고 탐구 질문을 정한 뒤 '이 주제로 자료 단계 시작'을 누릅니다.", items: ["조언은 탐구 방향과 다듬는 방법만 줍니다. 무엇을 탐구할지는 학생이 정합니다."], target: "#a-start" };
    }
    if (S.step === 1) return { title: "자료 살펴보기", message: "출처와 항목 카드를 읽고 '이 자료로 분석하기'를 누릅니다.", items: [tip.intro || "", "항목 카드에는 각 열의 뜻, 단위, 읽을 때 주의할 점이 있습니다."].filter(Boolean), target: S.dataOk ? "#next" : "#a-data" };
    if (S.step === 2) {
      if (!S.opened.length) return { title: "분석 실행", message: "추천 분석 하나를 눌러 실행합니다. 결과 카드가 아래에 생깁니다.", items: [tip.intro || ""].filter(Boolean), target: "[data-run]" };
      const last = S.opened[S.opened.length - 1];
      if (!S.hints[last]) return { title: "결과 읽기", message: "'관찰점, 유도 질문 불러오기'를 눌러 무엇을 볼지 안내를 받습니다. 결론은 학생이 씁니다.", target: `[data-hint="${last}"]` };
      if (!(S.interp[last] || "").trim()) return { title: "해석 쓰기", message: "결과에서 읽은 수치를 넣어 해석을 씁니다. 관찰한 사실, 근거 수치, 말할 수 있는 범위를 나눠 적어 보세요.", target: `[data-interp="${last}"]` };
      if (!S.feedback[last]) return { title: "AI 피드백 받기", message: "'AI 피드백 받기'를 눌러 잘한 점과 보완할 점을 봅니다. 피드백은 해석을 대신 써 주지 않습니다.", target: `[data-fb="${last}"]` };
      if (!S.saved[last]) return { title: "해석 저장", message: "피드백을 보고 고쳐 쓴 뒤 '해석 저장'을 누릅니다. 저장한 해석은 보고서에 실립니다.", target: `[data-save="${last}"]` };
      return { title: "더 분석하거나 보고서로", message: "다른 분석도 실행해 보거나, '다음'을 눌러 보고서를 만듭니다.", items: [((tip.insight || {})[s.analyses[last].tool]) || ""].filter(Boolean), target: "#next" };
    }
    if (S.step === 3) {
      if (!S.conclusion.trim()) return { title: "결론 쓰기", message: "저장한 해석을 이어 붙여 초안을 넣은 뒤 결론으로 다듬습니다. 이 자료로 말할 수 없는 것도 함께 씁니다.", target: "#a-draft" };
      if (!S.reportSaved) return { title: "보고서 저장", message: "결론을 다듬었으면 '보고서 저장'을 누릅니다.", target: "#a-report" };
      return { title: "피드백으로", message: "'다음'을 눌러 피드백 단계로 갑니다.", target: "#next" };
    }
    return { title: "돌아보기", message: "자기 성찰을 적고 저장합니다. 다른 시나리오도 체험해 보세요.", target: S.reflectSaved ? "#a-other" : "#a-reflect" };
  }

  function renderGuide() {
    const g = $("#guide");
    if (focused) focused.classList.remove("focus");
    focused = null;
    const visible = S.guideOn && S.scen !== null && !$(".backdrop");
    document.body.classList.toggle("guide-on", Boolean(visible && !S.collapsed));
    $("#guide-toggle").textContent = S.guideOn ? "안내 끄기" : "안내 켜기";
    if (!visible) {
      g.hidden = true;
      return;
    }
    const task = guideTask();
    const key = `${S.step}:${task.title}`;
    const prev = g.dataset.key;
    g.hidden = false;
    g.className = `guide${S.collapsed ? " collapsed" : ""}`;
    g.innerHTML = `<div class="guide-head"><span class="eyebrow">체험 안내  ${S.step + 1}/5 ${esc(STEPS[S.step])}</span><span><button type="button" id="g-col">${S.collapsed ? "펼치기" : "접기"}</button> <button type="button" id="g-off">끄기</button></span></div>
      <div class="guide-body"><h3>${esc(task.title)}</h3><p>${esc(task.message)}</p>${(task.items || []).length ? `<ul>${task.items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      <ul class="milestones">${milestones().map(([l, d]) => `<li class="${d ? "done" : ""}">${esc(l)}</li>`).join("")}</ul></div>`;
    g.dataset.key = key;
    if (prev && prev !== key) {
      g.classList.remove("guide-flash");
      void g.offsetWidth;
      g.classList.add("guide-flash");
    }
    $("#g-col").onclick = () => { S.collapsed = !S.collapsed; save(); renderGuide(); };
    $("#g-off").onclick = () => { S.guideOn = false; save(); renderGuide(); };
    const el = task.target ? document.querySelector(task.target) : null;
    if (el && !S.collapsed) {
      el.classList.add("focus");
      focused = el;
    }
  }

  function dialog(html, onMount) {
    $("#dialog-root").innerHTML = `<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true">${html}</div></div>`;
    renderGuide();
    if (onMount) onMount($("#dialog-root .dialog"));
  }

  function welcome() {
    dialog(
      `<h2>통계 에이전트 체험판</h2>
      <p>학생이 스스로 주제를 정해 자료, 분석, 보고서까지 가는 자유 탐구 화면을 대표 시나리오 셋으로 옮겼습니다. 로그인이나 서버 없이 이 브라우저 안에서만 돌아갑니다.</p>
      <ol>
        <li><b>주제:</b> 궁금한 것을 적으면 AI가 탐구 질문 후보를 조언합니다.</li>
        <li><b>자료:</b> 출처가 분명한 실제 공개 자료와 항목 카드를 봅니다.</li>
        <li><b>분석:</b> 교육과정 범위의 분석 도구만 실행되고, 결과 아래에 학생이 해석을 씁니다.</li>
        <li><b>보고서와 피드백:</b> 저장한 해석으로 A4 포스터를 만들고 돌아봅니다.</li>
      </ol>
      <p class="muted">분석 결과는 실제 앱의 도구로 미리 계산했습니다. AI 조언, 관찰점, 해석 피드백은 생성형 AI 대신 앱에 들어 있는 규칙 기반 안내로 보여 줍니다.</p>
      <div class="track-pick">${DATA.scenarios
        .map((s, i) => `<button type="button" data-scen="${i}"><b>${esc(s.title)}</b><small>${esc(LEVEL[s.level])}, ${esc(s.dataset.name)}</small></button>`)
        .join("")}</div>`,
      (root) =>
        root.querySelectorAll("[data-scen]").forEach((b) =>
          b.addEventListener("click", () => {
            const keep = { guideOn: S.guideOn };
            S = { ...fresh(), ...keep, scen: Number(b.dataset.scen) };
            $("#dialog-root").innerHTML = "";
            render();
          }),
        ),
    );
  }

  $("#prev").addEventListener("click", () => go(S.step - 1));
  $("#next").addEventListener("click", () => go(S.step + 1));
  $("#restart").addEventListener("click", () => welcome());
  $("#guide-toggle").addEventListener("click", () => { S.guideOn = !S.guideOn; S.collapsed = false; save(); renderGuide(); });

  if (S.scen !== null && DATA.scenarios[S.scen]) render();
  else welcome();
})();
