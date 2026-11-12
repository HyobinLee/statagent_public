(function () {
  "use strict";

  const DATA = window.DEMO_DATA;
  const STORE_KEY = "stat-agent-demo";
  const STAT_LABELS = { mean: "평균", median: "중앙값", mode: "최빈값", std: "표준편차", range: "범위", min: "최솟값", max: "최댓값", q1: "제1사분위수", q3: "제3사분위수" };
  const TRACK_INFO = {
    m1: "두 반 단원평가 비교로 대푯값을 읽고, 전국 중학생 사교육비 분포를 살펴봅니다.",
    high: "방과후 수학 두 반의 평균이 나눠 보면 뒤집히는 장면(심슨의 역설)을 체험합니다.",
    gifted: "두 학급의 1.2점 차이를 반 라벨을 1000번 섞은 분포 위에서 읽어 봅니다.",
  };

  const TIPS = {
    "m1:compare_classes": { ask: "평균은 A반이 높은데 중앙값과 최빈값은 B반이 높습니다. 왜 그럴까요? 표에서 무엇이 보이나요?" },
    "gifted:compare_classes": { ask: "평균은 A반, 중앙값은 B반이 높습니다. 표준편차는 어느 쪽이 큰가요? 그 뜻은 무엇일까요?" },
    rep_values: { info: "선생님은 여기서 세 대푯값의 뜻만 확인합니다. 어떤 대푯값으로 말해야 하는지는 확인 문제를 푼 뒤에 정리합니다." },
    rep_hinge: { after: "A반 평균이 높았던 것은 반 전체가 고르게 잘해서가 아니라 만점 3명이 평균을 끌어올렸기 때문입니다. 평균은 아주 큰 값이나 작은 값에 끌려가고, 중앙값은 잘 흔들리지 않습니다. 그래서 대푯값을 말할 때는 '평균으로는, 중앙값으로는'처럼 어떤 수인지 함께 말합니다." },
    concept: { info: "'반은 추첨이 아니라 학생이 스스로 골랐다'는 문장을 기억해 두세요. 왜 중요한지는 뒤에서 나옵니다." },
    overall_predict: { ask: "전체로 보면 대면반, 나눠 보면 온라인반이 앞섭니다. 같은 자료에서 어떻게 반대 결론이 나올 수 있을까요?" },
    why_simpson: { ask: "그렇다면 대면반 전체 평균이 컸던 까닭은 무엇일까요? 다음 확인 문제에서 골라 봅니다." },
    simpson_hinge: { after: "전체 평균은 집단별 평균을 인원수만큼 무겁게 쳐서 합친 가중평균입니다. 온라인반은 (90명 × 5점 + 10명 × 13점) ÷ 100명 = 5.8점, 대면반은 (10명 × 3점 + 90명 × 11점) ÷ 100명 = 10.2점입니다. 대면반 전체 평균이 컸던 것은 향상폭이 큰 하위권이 90명이나 몰려 있었기 때문입니다. 다만 반을 학생이 스스로 골랐으므로 '효과가 증명되었다'고까지는 말할 수 없습니다." },
    g_resample_intro: { info: "같은 60명을 30명씩 나누는 방법은 아주 많습니다. 나눌 때마다 평균 차이가 얼마나 흔들리는지가 오늘의 질문입니다." },
    g_resample_run: { ask: "세로선(관찰된 +1.2점)은 분포의 가운데와 끝자락 중 어디에 가까운가요?", after: "이 그림은 우연만으로 생기는 차이의 범위를 보여 줄 뿐, 어느 쪽이라고 정해 주지는 않습니다." },
    g_resample_hinge_card: { after: "가운데 부근에 있다는 것은 반이 점수와 무관해도 흔히 나는 크기의 차이라는 뜻입니다. 그렇다고 두 반 실력이 같다는 것이 증명된 것도 아닙니다. 증거가 약한 것과 차이가 없다는 증명은 다른 말입니다." },
    x2_l1_wrapup_card: { info: "실제 수업에서는 학생이 먼저 한 줄을 쓰고, 선생님이 응답 두세 개를 읽어 준 뒤 '선생님의 한 줄'을 엽니다." },
    x2d_intro: { ask: "학원, 과외, 학습지처럼 학교 밖에서 돈을 내고 하는 공부를 사교육이라고 합니다. 전국 중학생이 여기에 한 달에 얼마나 쓸지 짐작이 가나요?" },
    x2d_predict: { info: "선생님 화면에는 반 전체의 예측이 점그림으로 모입니다. 예측의 근거가 '우리 반'인 학생이 많은지도 봅니다." },
    x2d_source: { after: "이 조사는 국가데이터처가 교육부와 함께 하는 표본조사입니다. B는 그 조사가 쓰는 방법이고, 우리가 할 일은 이미 나와 있는 결과를 찾는 것이라 C입니다." },
    x2d_fetch: { info: "실제 수업에서는 에이전트가 KOSIS에 요청을 보내 표를 바로 받아옵니다. 체험판은 미리 받아 둔 같은 표(2025년)를 보여 줍니다.", ask: "중학교 줄에서 가장 큰 숫자는 어느 구간에 있나요? 두 번째는요?" },
    x2d_reveal: { after: "평균 표의 평균은 사교육을 받지 않는 학생도 0원으로 넣고 나눈 값입니다. 받지 않는 학생이 늘어도 받는 학생이 더 많이 쓰면 평균은 오릅니다. 에이전트 초안의 ③은 평균 하나를 모두에게 씌운 문장입니다. 40~50만 원 구간은 100명 중 약 8명뿐입니다." },
    x2d_evidence: { after: "이 자료는 전국 중학생 표본의 결과입니다. 우리 반이 전국과 꼭 같다고도, 전혀 다르다고도 말할 수 없습니다. 전국은 이렇다고까지만 말할 수 있습니다." },
    x2d_income_card: { after: "소득이 높은 가구의 학생이 사교육비를 많이 쓰는 경향은 보입니다. 그러나 이 표만으로 소득이 원인이라고 말할 수는 없습니다. 지역, 학년, 부모의 교육관처럼 함께 움직이는 요인이 있습니다." },
    diag_pre_intro: { info: "점수에 들어가지 않습니다. 모르면 짐작으로 고르고 확신도를 낮게 두면 됩니다." },
    diag_post_intro: { info: "첫 시간과 비슷한 문항입니다. 이번에는 이유를 직접 씁니다." },
  };

  const PROMPT_HELP = {
    predict: "결과를 보기 전에 먼저 예측합니다. 생각과 이유를 쓰고 '예측 보내기'를 누르세요. 보내야 결과 열기 버튼이 풀립니다.",
    predict_pair: "숫자 두 개를 어림해 적고, 그렇게 생각한 이유를 쓴 뒤 보냅니다.",
    hinge: "보기 하나를 고르고, 그렇게 고른 이유를 한 문장 이상 씁니다. 이유가 없으면 보내지지 않습니다.",
    evidence: "결과에서 읽은 숫자를 하나 이상 넣어 씁니다. 숫자가 없으면 보내지지 않습니다.",
    exit: "오늘 알게 된 것이나 달라진 생각을 한 문장으로 씁니다.",
  };
  const SEND_LABEL = { predict: "예측 보내기", predict_pair: "예측 보내기", hinge: "선택과 이유 보내기", evidence: "보내기", exit: "보내기" };

  let S = load() || fresh();
  let focused = null;

  function fresh() {
    return { track: null, lesson: 0, idx: 0, diagMode: "two", guideOn: true, collapsed: false, answers: {} };
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
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function rich(v) {
    return esc(v).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }
  function fmt(v) {
    if (Array.isArray(v)) return v.map(fmt).join(", ");
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
    return esc(v);
  }

  function lessonData() {
    return DATA.tracks[S.track].lessons[S.lesson];
  }
  function cards() {
    const all = lessonData().cards;
    if (S.diagMode === "all") return all;
    if (S.diagMode === "skip") return all.filter((c) => c.kind !== "diag" && !/^diag_(pre|post)_intro$/.test(c.id));
    const out = [];
    let run = 0;
    for (const c of all) {
      if (c.kind === "diag") {
        run += 1;
        if (run > 2) continue;
      } else {
        run = 0;
      }
      out.push(c);
    }
    return out;
  }
  function card() {
    return cards()[S.idx];
  }
  function uid(c) {
    return `${S.track}:${S.lesson}:${c.id}`;
  }
  function rec(c) {
    const k = uid(c);
    if (!S.answers[k]) S.answers[k] = { prompts: {}, opened: [], diag: {}, loaded: false };
    return S.answers[k];
  }
  function tip(c) {
    return TIPS[`${S.track}:${c.id}`] || TIPS[c.id] || {};
  }

  function promptState(c, p) {
    const r = rec(c);
    if (!r.prompts[p.prompt_id]) r.prompts[p.prompt_id] = { draft: "", choice: "", nums: {}, sent: null, resubDraft: "", resub: null };
    return r.prompts[p.prompt_id];
  }
  function firstPromptSent(c) {
    const ps = c.prompts || [];
    return ps.length === 0 || ps.every((p) => promptState(c, p).sent);
  }
  function revealAvailable(c, r) {
    return r.open_before_answer || firstPromptSent(c);
  }
  function needsResubmit(c, p) {
    return p.requires_resubmit && (c.reveals || []).length > 0;
  }
  function cardDone(c) {
    const r = rec(c);
    if (c.kind === "diag") return Boolean(r.diag.saved);
    if (c.kind === "connector") return r.loaded;
    for (const p of c.prompts || []) {
      const st = promptState(c, p);
      if (!st.sent) return false;
      if (needsResubmit(c, p) && !st.resub) return false;
    }
    return true;
  }

  function resultHtml(lesson, key) {
    const res = lesson.results[key];
    if (!res) return "";
    const data = res.result && res.result.data ? res.result.data : {};
    if (res.charts && res.charts.length) {
      return `<img src="${res.charts[0]}" alt="${esc(data.alt_text || "에이전트가 그린 그림")}">`;
    }
    if (data.groups) {
      const cols = data.columns || [];
      const stats = [];
      cols.forEach((col) => Object.keys((data.groups[0].statistics || {})[col] || {}).forEach((s) => stats.push([col, s])));
      const reveal = findReveal(lesson, key) || {};
      const head = [esc(data.group_by), esc(reveal.count_label || "학생 수")].concat(stats.map(([, s]) => esc(STAT_LABELS[s] || s)));
      const rows = data.groups.map((g) => [esc(g.group), fmt(g.sample_size ?? g.row_count)].concat(stats.map(([col, s]) => fmt(g.statistics[col][s]))));
      return tableHtml(head, rows, true);
    }
    return `<pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
  }
  function findReveal(lesson, key) {
    for (const c of lesson.cards) for (const r of c.reveals || []) if (r.key === key) return r;
    return null;
  }
  function tableHtml(head, rows, safe) {
    const cell = (v) => (safe ? v : esc(v));
    return `<div class="scroll"><table><thead><tr>${head.map((h) => `<th>${cell(h)}</th>`).join("")}</tr></thead><tbody>${rows
      .map((r) => `<tr>${r.map((v) => `<td>${cell(v)}</td>`).join("")}</tr>`)
      .join("")}</tbody></table></div>`;
  }
  function revealBody(lesson, r) {
    let html = "";
    if (r.teacher_only) html += `<span class="tag">실제 수업에서는 선생님이 여는 내용</span>`;
    if (r.tool_name) html += resultHtml(lesson, r.key);
    (r.text || []).forEach((t) => (html += `<p>${rich(t)}</p>`));
    if (r.text_rows) html += tableHtml(r.text_rows[0], r.text_rows.slice(1), false);
    if (r.figure) html += `<figure><img src="${r.figure}" alt="${esc(r.figure_alt || "")}"></figure>`;
    if (r.note) html += `<div class="note">${rich(r.note)}</div>`;
    return html;
  }

  function sheetHtml(c, lesson) {
    if (c.side_panel !== "sheet" || !lesson.dataset) return "";
    const ds = lesson.dataset;
    const limit = Math.min(ds.rows.length, c.sheet_limit || 60);
    return `<aside class="sheet"><h3>자료 표 (${ds.rows.length}행)</h3>${tableHtml(ds.columns, ds.rows.slice(0, limit), false)}<p class="muted">${esc(lesson.dataset_source || "")}</p></aside>`;
  }

  function promptHtml(c, p, i) {
    const st = promptState(c, p);
    const type = p.type || "exit";
    const id = `p${i}`;
    let html = `<div class="prompt" data-prompt="${i}"><div class="q">${rich(p.question)}</div>`;
    const sent = st.sent;
    if (type === "hinge") {
      html += `<div class="choices">${(p.choices || [])
        .map(
          (ch) =>
            `<label class="choice"><input type="radio" name="${id}-c" value="${esc(ch.key)}" ${st.choice === ch.key ? "checked" : ""} ${sent ? "disabled" : ""}> <span><b>${esc(ch.key)}.</b> ${rich(ch.label)}</span></label>`,
        )
        .join("")}</div>`;
    }
    if (type === "predict_pair") {
      html += `<div class="pair">${(p.fields || [])
        .map(
          (f) =>
            `<label>${esc(f.label)} (${esc(f.unit)})<input type="number" min="${f.min}" max="${f.max}" data-num="${esc(f.key)}" value="${esc(st.nums[f.key] ?? "")}" ${sent ? "disabled" : ""}></label>`,
        )
        .join("")}</div>`;
    }
    html += `<textarea id="${id}-t" placeholder="${esc(p.placeholder || "")}" ${sent ? "disabled" : ""}>${esc(sent ? sent.text : st.draft)}</textarea>`;
    if (sent) {
      html += `<div class="row"><span class="sent">✓ 보냈습니다</span></div>`;
      if (type === "predict" && (c.reveals || []).length) html += `<div class="locked-note">결과를 연 뒤에는 처음 예측을 고칠 수 없습니다. 바뀐 생각은 아래 '다시 보내기' 칸에 씁니다.</div>`;
    } else {
      html += `<div class="row"><button type="button" class="primary" id="${id}-send">${SEND_LABEL[type] || "보내기"}</button><span class="error" id="${id}-err"></span></div>`;
    }
    if (sent && needsResubmit(c, p) && rec(c).opened.length > 0) {
      html += `<div class="resubmit"><div class="q">결과를 확인했습니다. 처음 예측을 유지하나요, 고치나요? 결과에서 본 수치를 근거로 다시 보내 주세요.</div>`;
      html += `<textarea id="${id}-r" ${st.resub ? "disabled" : ""}>${esc(st.resub || st.resubDraft)}</textarea>`;
      html += st.resub
        ? `<div class="row"><span class="sent">✓ 다시 보냈습니다</span></div>`
        : `<div class="row"><button type="button" class="primary" id="${id}-rsend">다시 보내기</button><span class="error" id="${id}-rerr"></span></div>`;
      html += `</div>`;
    }
    return html + `</div>`;
  }

  function diagHtml(c) {
    const it = c.item;
    const d = rec(c).diag;
    const saved = d.saved;
    let html = `<div class="prompt"><div class="q">${rich(it.question)}</div><div class="choices">`;
    html += it.choices
      .map((ch) => `<label class="choice"><input type="radio" name="dc" value="${esc(ch.key)}" ${d.choice === ch.key ? "checked" : ""} ${saved ? "disabled" : ""}> <span>${esc(ch.key)} ${rich(ch.label)}</span></label>`)
      .join("");
    html += `</div>`;
    if (it.reason_choices && it.reason_choices.length) {
      html += `<div class="q">그렇게 생각한 이유</div><div class="choices">`;
      html += it.reason_choices
        .map((ch) => `<label class="choice"><input type="radio" name="dr" value="${esc(ch.key)}" ${d.reason === ch.key ? "checked" : ""} ${saved ? "disabled" : ""}> <span>${esc(ch.key)} ${rich(ch.label)}</span></label>`)
        .join("");
      html += `<label class="choice"><input type="radio" name="dr" value="direct" ${d.reason === "direct" ? "checked" : ""} ${saved ? "disabled" : ""}> <span>직접 쓰기</span></label></div>`;
      if (d.reason === "direct") html += `<textarea id="d-text" placeholder="이유를 적어 주세요." ${saved ? "disabled" : ""}>${esc(d.text || "")}</textarea>`;
    } else {
      html += `<div class="q">그렇게 생각한 이유를 직접 쓰세요</div><textarea id="d-text" ${saved ? "disabled" : ""}>${esc(d.text || "")}</textarea>`;
    }
    html += `<div class="q" style="margin-top:.8rem">이 답에 얼마나 확신하나요?</div><div class="confidence">`;
    [1, 2, 3, 4].forEach((n) => {
      const label = { 1: "1 전혀 확신 없음", 2: "2", 3: "3", 4: "4 매우 확신" }[n];
      html += `<label><input type="radio" name="dconf" value="${n}" ${String(d.conf) === String(n) ? "checked" : ""} ${saved ? "disabled" : ""}> ${label}</label>`;
    });
    html += `</div>`;
    html += saved
      ? `<div class="row"><span class="sent">✓ 저장했습니다</span></div>`
      : `<div class="row"><button type="button" class="primary" id="d-save">저장</button><span class="error" id="d-err"></span></div>`;
    return html + `</div>`;
  }

  function render() {
    const lesson = lessonData();
    const list = cards();
    const c = card();
    const r = rec(c);
    $("#track-label").textContent = `${DATA.tracks[S.track].label}, ${S.lesson + 1}차시: ${lesson.title}`;
    $("#progress-label").textContent = `${S.lesson + 1}차시  카드 ${S.idx + 1} / ${list.length}`;
    $("#progress-fill").style.width = `${((S.idx + 1) / list.length) * 100}%`;

    let html = `<div class="card">`;
    if (c.group && c.group !== c.title) html += `<p class="group">${esc(c.group)}</p>`;
    html += `<h2>${esc(c.title || "")}</h2>`;
    (c.body || []).forEach((b) => (html += `<p>${rich(b)}</p>`));
    if (c.figure) html += `<figure><img src="${c.figure}" alt="${esc(c.figure_alt || "")}"><figcaption>${esc(c.figure_alt || "")}</figcaption></figure>`;

    if (c.context_reveals && c.context_reveals.length) {
      html += `<div class="reveals"><div class="muted">앞에서 연 결과</div>${c.context_reveals
        .map((k) => `<div class="reveal">${revealBody(lesson, findReveal(lesson, k) || { key: k, tool_name: "x" })}</div>`)
        .join("")}</div>`;
    }

    if (c.kind === "diag") html += diagHtml(c);

    if (c.kind === "connector") {
      if (r.loaded) {
        html += `<span class="conn-badge">대체 자료 사용 (체험판: 미리 받아 둔 KOSIS 2025년 표)</span>`;
        html += tableHtml(DATA.kosis.columns, DATA.kosis.rows, false);
        if (c.note) html += `<p class="muted">${rich(c.note)}</p>`;
      } else {
        html += `<div class="row"><button type="button" class="primary" id="conn-load">자료 불러오기</button></div>`;
      }
    }

    (c.prompts || []).forEach((p, i) => (html += promptHtml(c, p, i)));

    if ((c.reveals || []).length) {
      html += `<div class="reveals">`;
      c.reveals.forEach((rv, i) => {
        if (r.opened.includes(rv.key)) {
          html += `<div class="reveal">${revealBody(lesson, rv)}</div>`;
        } else {
          const ok = revealAvailable(c, rv);
          html += `<button type="button" class="reveal-btn" data-reveal="${i}" ${ok ? "" : "disabled"}>${esc(rv.label)}</button>`;
          if (!ok) html += `<span class="muted">위의 답을 보내면 열 수 있습니다.</span>`;
        }
      });
      html += `</div>`;
    }
    if (c.footer && (!c.footer_after || r.opened.includes(c.footer_after))) {
      html += `<div class="footer-text">${c.footer.map((f) => `<p>${rich(f)}</p>`).join("")}</div>`;
    }
    html += `</div>`;

    const sheet = sheetHtml(c, lesson);
    $("#stage").innerHTML = sheet ? `<div class="layout with-sheet">${sheet}${html}</div>` : `<div class="layout">${html}</div>`;
    $("#prev").disabled = S.idx === 0 && S.lesson === 0;
    $("#next").disabled = !cardDone(c);
    bind(c);
    save();
    renderGuide();
  }

  function bind(c) {
    const r = rec(c);
    (c.prompts || []).forEach((p, i) => {
      const st = promptState(c, p);
      const ta = $(`#p${i}-t`);
      if (ta && !st.sent) ta.addEventListener("input", () => { st.draft = ta.value; save(); renderGuide(); });
      document.querySelectorAll(`input[name="p${i}-c"]`).forEach((el) => el.addEventListener("change", () => { st.choice = el.value; save(); renderGuide(); }));
      document.querySelectorAll(`[data-prompt="${i}"] [data-num]`).forEach((el) => el.addEventListener("input", () => { st.nums[el.dataset.num] = el.value; save(); renderGuide(); }));
      const send = $(`#p${i}-send`);
      if (send) send.addEventListener("click", () => sendPrompt(c, p, i));
      const rt = $(`#p${i}-r`);
      if (rt && !st.resub) rt.addEventListener("input", () => { st.resubDraft = rt.value; save(); renderGuide(); });
      const rs = $(`#p${i}-rsend`);
      if (rs) rs.addEventListener("click", () => {
        const v = (st.resubDraft || "").trim();
        if (!v) { $(`#p${i}-rerr`).textContent = "바뀐 생각이나 유지하는 이유를 적어 주세요."; return; }
        st.resub = v;
        render();
      });
    });
    document.querySelectorAll("[data-reveal]").forEach((b) =>
      b.addEventListener("click", () => {
        const rv = c.reveals[Number(b.dataset.reveal)];
        if (!r.opened.includes(rv.key)) r.opened.push(rv.key);
        render();
      }),
    );
    const conn = $("#conn-load");
    if (conn) conn.addEventListener("click", () => { r.loaded = true; render(); });
    if (c.kind === "diag") {
      const d = r.diag;
      document.querySelectorAll('input[name="dc"]').forEach((el) => el.addEventListener("change", () => { d.choice = el.value; save(); renderGuide(); }));
      document.querySelectorAll('input[name="dr"]').forEach((el) => el.addEventListener("change", () => { d.reason = el.value; render(); }));
      document.querySelectorAll('input[name="dconf"]').forEach((el) => el.addEventListener("change", () => { d.conf = el.value; save(); renderGuide(); }));
      const t = $("#d-text");
      if (t) t.addEventListener("input", () => { d.text = t.value; save(); renderGuide(); });
      const sv = $("#d-save");
      if (sv) sv.addEventListener("click", () => {
        const needText = !(c.item.reason_choices && c.item.reason_choices.length) || d.reason === "direct";
        if (!d.choice) return void ($("#d-err").textContent = "답을 골라 주세요.");
        if (!needText && !d.reason) return void ($("#d-err").textContent = "이유를 골라 주세요.");
        if (needText && !(d.text || "").trim()) return void ($("#d-err").textContent = "이유를 적어 주세요.");
        if (!d.conf) return void ($("#d-err").textContent = "확신도를 골라 주세요.");
        d.saved = true;
        render();
      });
    }
  }

  function sendPrompt(c, p, i) {
    const st = promptState(c, p);
    const err = $(`#p${i}-err`);
    const text = (st.draft || "").trim();
    if (p.type === "hinge" && !st.choice) return void (err.textContent = "보기를 하나 골라 주세요.");
    if (p.type === "predict_pair") {
      for (const f of p.fields || []) {
        const v = Number(st.nums[f.key]);
        if (st.nums[f.key] === undefined || st.nums[f.key] === "" || Number.isNaN(v) || v < f.min || v > f.max) {
          return void (err.textContent = `${f.short || f.label}에 ${f.min}~${f.max} 사이의 숫자를 넣어 주세요.`);
        }
      }
    }
    if (!text) return void (err.textContent = p.type === "hinge" ? "고른 이유를 적어 주세요." : "답을 적어 주세요.");
    if (p.type === "evidence" && !/\d/.test(text)) return void (err.textContent = "값을 하나 이상 넣어 주세요.");
    st.sent = { text, choice: st.choice, nums: { ...st.nums } };
    render();
  }

  function guideTask() {
    const c = card();
    const r = rec(c);
    const t = tip(c);
    const task = { title: c.title || "", message: "", items: [], target: null, teacher: null };
    if (c.kind === "diag") {
      const d = r.diag;
      if (!d.saved) {
        task.title = "생각 확인 문항";
        task.message = "답을 고르고, 이유를 고르거나 직접 쓰고, 확신도를 1부터 4 가운데 표시한 뒤 '저장'을 누릅니다. 채점 결과는 학생 화면에 보이지 않습니다.";
        task.target = !d.choice ? ".choices" : !d.conf ? ".confidence" : "#d-save";
        if (S.diagMode === "two") task.items.push("체험판에서는 각 확인을 앞 두 문항만 봅니다. 실제 수업은 6문항이나 9문항입니다.");
        return task;
      }
    }
    if (c.kind === "connector" && !r.loaded) {
      task.message = "'자료 불러오기'를 눌러 에이전트가 가져온 표를 봅니다.";
      task.target = "#conn-load";
      if (t.info) task.items.push(t.info);
      return task;
    }
    const ps = c.prompts || [];
    for (let i = 0; i < ps.length; i += 1) {
      const p = ps[i];
      const st = promptState(c, p);
      if (!st.sent) {
        task.message = PROMPT_HELP[p.type] || PROMPT_HELP.exit;
        const ready = (st.draft || "").trim() && (p.type !== "hinge" || st.choice);
        task.target = ready ? `#p${i}-send` : p.type === "hinge" && !st.choice ? `[data-prompt="${i}"] .choices` : p.type === "predict_pair" ? `[data-prompt="${i}"] .pair` : `#p${i}-t`;
        if (t.ask) task.teacher = { label: "선생님이 묻는 말", text: t.ask };
        if (t.info) task.items.push(t.info);
        return task;
      }
    }
    const rv = (c.reveals || []).find((x) => !r.opened.includes(x.key) && revealAvailable(c, x));
    const resubPending = ps.find((p) => needsResubmit(c, p) && !promptState(c, p).resub);
    if (rv) {
      task.message = rv.teacher_only
        ? `실제 수업에서는 선생님이 학생 답을 두세 개 읽어 준 뒤 '${rv.label}'을 누릅니다. 체험판에서는 직접 눌러 보세요.`
        : `'${rv.label}'을 눌러 에이전트가 계산한 결과를 엽니다.`;
      if (ps.length && !rv.open_before_answer) task.items.push("답을 보낸 학생에게만 결과가 펼쳐집니다(답 잠금). 남의 답이나 결과를 보고 쓰지 않도록 한 장치입니다.");
      task.target = `[data-reveal="${c.reveals.indexOf(rv)}"]`;
      if (t.ask && r.opened.length) task.teacher = { label: "선생님이 묻는 말", text: t.ask };
      return task;
    }
    if (resubPending) {
      const i = ps.indexOf(resubPending);
      task.message = "결과를 보고 생각을 다시 씁니다. 처음 예측은 잠겼고, 바뀐 생각은 이 칸에 따로 남습니다. 선생님 화면에는 학생마다 처음 생각과 바뀐 생각이 나란히 보입니다.";
      task.target = (promptState(c, resubPending).resubDraft || "").trim() ? `#p${i}-rsend` : `#p${i}-r`;
      if (t.ask) task.teacher = { label: "선생님이 묻는 말", text: t.ask };
      return task;
    }
    task.message = isLastCard() ? "이 차시의 마지막 카드입니다. '다음'을 누르면 정리 화면이 나옵니다." : "이 카드를 마쳤습니다. '다음'을 눌러 넘어갑니다.";
    task.target = "#next";
    if (t.after) task.teacher = { label: "답을 받은 뒤 선생님이 정리하는 말", text: t.after };
    else if (t.ask && !ps.length) task.teacher = { label: "선생님이 묻는 말", text: t.ask };
    if (t.info && !ps.length) task.items.push(t.info);
    return task;
  }

  function milestones() {
    const list = cards();
    const groups = [
      ["생각 확인", (c) => c.kind === "diag"],
      ["예측", (c) => (c.prompts || []).some((p) => p.type === "predict" || p.type === "predict_pair")],
      ["자료", (c) => c.kind === "connector"],
      ["확인 문제", (c) => (c.prompts || []).some((p) => p.type === "hinge")],
      ["근거 쓰기", (c) => (c.prompts || []).some((p) => p.type === "evidence")],
      ["마무리", (c) => (c.prompts || []).some((p) => p.type === "exit")],
    ];
    return groups
      .map(([label, fn]) => {
        const cs = list.filter(fn);
        return cs.length ? { label, done: cs.every(cardDone) } : null;
      })
      .filter(Boolean);
  }

  function renderGuide() {
    const g = $("#guide");
    if (focused) focused.classList.remove("focus");
    focused = null;
    const visible = S.guideOn && S.track && !$(".backdrop");
    document.body.classList.toggle("guide-on", Boolean(visible && !S.collapsed));
    if (!visible) {
      g.hidden = true;
      $("#guide-toggle").textContent = S.guideOn ? "안내 끄기" : "안내 켜기";
      return;
    }
    $("#guide-toggle").textContent = "안내 끄기";
    const task = guideTask();
    const prevTitle = g.dataset.key;
    const key = `${S.lesson}:${S.idx}:${task.message}`;
    g.hidden = false;
    g.className = `guide${S.collapsed ? " collapsed" : ""}`;
    g.innerHTML = `<div class="guide-head"><span class="eyebrow">체험 안내  ${S.lesson + 1}차시 ${S.idx + 1}/${cards().length}</span><span><button type="button" id="g-col">${S.collapsed ? "펼치기" : "접기"}</button> <button type="button" id="g-off">끄기</button></span></div>
      <div class="guide-body"><h3>${esc(task.title)}</h3><p>${esc(task.message)}</p>
      ${task.items.length ? `<ul>${task.items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${task.teacher ? `<div class="teacher"><strong>${esc(task.teacher.label)}</strong>${esc(task.teacher.text)}</div>` : ""}
      <ul class="milestones">${milestones().map((m) => `<li class="${m.done ? "done" : ""}">${esc(m.label)}</li>`).join("")}</ul></div>`;
    g.dataset.key = key;
    if (prevTitle && prevTitle !== key) {
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

  function isLastCard() {
    return S.idx === cards().length - 1;
  }

  function dialog(html, onMount) {
    $("#dialog-root").innerHTML = `<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true">${html}</div></div>`;
    renderGuide();
    if (onMount) onMount($("#dialog-root .dialog"));
  }
  function closeDialog() {
    $("#dialog-root").innerHTML = "";
    renderGuide();
  }

  function welcome() {
    dialog(
      `<h2>통계 에이전트 체험판</h2>
      <p>2026년 실험수업(2차시)에 쓴 학생 화면을 그대로 옮겼습니다. 로그인이나 서버 없이 이 브라우저 안에서만 돌아가며, 쓴 답은 어디에도 보내지 않습니다.</p>
      <ol>
        <li>결과를 보기 전에 먼저 <b>예측</b>을 보냅니다. 보내야 결과 열기 버튼이 풀립니다.</li>
        <li>결과는 에이전트가 계산합니다. 체험판에는 실제 수업과 같은 도구로 미리 계산한 결과가 들어 있습니다.</li>
        <li>결과를 본 뒤 생각을 <b>다시 보내기</b> 칸에 고쳐 씁니다. 처음 예측은 잠깁니다.</li>
        <li>오른쪽 아래 <b>안내</b>가 다음에 할 일과 선생님이 수업에서 하는 말을 알려 줍니다.</li>
      </ol>
      <div class="track-pick">${Object.entries(DATA.tracks)
        .map(([k, t]) => `<button type="button" data-track="${k}"><b>${esc(t.label)}</b><small>${esc(TRACK_INFO[k] || "")}</small></button>`)
        .join("")}</div>
      <div class="opt">생각 확인 문항(수업 전후 확인): <select id="diag-mode"><option value="two">앞 두 문항만 맛보기</option><option value="all">전부 풀기</option><option value="skip">건너뛰기</option></select></div>`,
      (root) => {
        root.querySelector("#diag-mode").value = S.diagMode;
        root.querySelectorAll("[data-track]").forEach((b) =>
          b.addEventListener("click", () => {
            const mode = root.querySelector("#diag-mode").value;
            S = fresh();
            S.track = b.dataset.track;
            S.diagMode = mode;
            closeDialog();
            render();
          }),
        );
      },
    );
  }

  function lessonSummary(lessonIdxs) {
    const items = [];
    const keep = S.lesson;
    const list = [];
    for (const li of lessonIdxs || [S.lesson]) {
      S.lesson = li;
      cards().forEach((c) => list.push([li, c]));
    }
    S.lesson = keep;
    for (const [li, c] of list) {
      S.lesson = li;
      for (const p of c.prompts || []) {
        const st = promptState(c, p);
        if (!st.sent) continue;
        if (p.type === "predict") items.push([`${c.title}: 처음 예측`, st.sent.text], ...(st.resub ? [[`${c.title}: 결과를 본 뒤`, st.resub]] : []));
        else if (p.type === "predict_pair") items.push([`${c.title}`, `${(p.fields || []).map((f) => `${f.short} ${st.sent.nums[f.key]}${f.unit}`).join(", ")}. ${st.sent.text}`]);
        else if (p.type === "hinge") items.push([`${c.title}: 고른 답 ${st.sent.choice}`, st.sent.text]);
        else items.push([c.title, st.sent.text]);
      }
    }
    S.lesson = keep;
    return `<div class="summary-list">${items.map(([a, b]) => `<div class="summary-item"><b>${esc(a)}</b>${esc(b)}</div>`).join("")}</div>`;
  }

  function finishLesson() {
    const last = S.lesson === DATA.tracks[S.track].lessons.length - 1;
    if (!last) {
      dialog(
        `<h2>${S.lesson + 1}차시를 마쳤습니다</h2><p>이번 차시에 쓴 답입니다. 실제 수업에서는 이 기록이 선생님의 응답 보드와 수업 뒤 개인 리포트로 이어집니다.</p>${lessonSummary()}
        <div class="row"><button type="button" class="primary" id="go-next">2차시 시작</button></div>`,
        (root) => root.querySelector("#go-next").addEventListener("click", () => { S.lesson += 1; S.idx = 0; closeDialog(); render(); }),
      );
    } else {
      dialog(
        `<h2>체험을 마쳤습니다</h2><p>두 차시 동안 쓴 답입니다. 처음 예측과 결과를 본 뒤의 생각이 어떻게 달라졌는지 견주어 보세요.</p>${lessonSummary(DATA.tracks[S.track].lessons.map((_, i) => i))}
        <p class="muted">이 체험판은 학생 화면만 보여 줍니다. 실제 앱에는 교사 진행 화면(학생 화면 모으기, 결과 공개, 응답 보드)과 학급 코드와 PIN 로그인이 있습니다.</p>
        <div class="row"><button type="button" class="primary" id="go-other">다른 과정 체험하기</button></div>`,
        (root) => root.querySelector("#go-other").addEventListener("click", () => welcome()),
      );
    }
  }

  $("#next").addEventListener("click", () => {
    if (!cardDone(card())) return;
    if (isLastCard()) return finishLesson();
    S.idx += 1;
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  $("#prev").addEventListener("click", () => {
    if (S.idx > 0) S.idx -= 1;
    else if (S.lesson > 0) { S.lesson -= 1; S.idx = cards().length - 1; }
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  $("#restart").addEventListener("click", () => welcome());
  $("#guide-toggle").addEventListener("click", () => { S.guideOn = !S.guideOn; S.collapsed = false; save(); renderGuide(); });

  if (S.track) render();
  else welcome();
})();
