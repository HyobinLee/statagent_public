(function () {
  "use strict";

  const DATA = window.DEMO_DATA;
  const TF = window.TEACHER_FIELDS;
  const SIM = window.TEACHER_SIM;
  const R = window.DemoResults;
  const esc = R.esc;
  const STORE_KEY = "stat-agent-demo-teacher";
  const JOIN_CODE = "DEMO26";
  const TRACK_LABEL = { m1: "중학교 1학년 과정", high: "고등학교 과정", gifted: "영재학교 과정" };

  const SCRIPT = {
    exp2_intro_card: { say: "오늘은 먼저 통계에 대해 어떻게 생각하는지 묻는 문항에 답합니다. 맞고 틀리고가 아니라 지금 생각을 보는 것입니다.", avoid: "실험, 연구, 오개념, 진단 같은 말은 수업 중에 쓰지 않습니다." },
    diag_pre_intro: { say: "모르겠으면 짐작으로 고르고 확신도를 낮게 두면 됩니다. 그게 솔직한 답입니다.", avoid: "문항 내용에 대한 힌트나 정답 방향을 말하지 않습니다." },
    "m1:compare_classes": { ask: "평균은 A반이 높은데 중앙값과 최빈값은 B반이 높습니다. 왜 그럴까요? 표에서 무엇이 보이나요?", avoid: "'만점 3명'은 말하지 않습니다. 다음 확인 문제의 공개에 들어 있습니다." },
    "gifted:compare_classes": { ask: "평균은 A반, 중앙값은 B반이 높습니다. 표준편차는 어느 쪽이 큰가요? 그 뜻은?", avoid: "'하나의 수만 보고 말하기 어렵다'는 결론은 학생이 말하게 합니다." },
    rep_values: { say: "세 대푯값이 각각 무엇인지 카드로 확인합니다.", avoid: "'평균은 큰 값에 끌려간다'는 성질은 확인 문제 뒤에 말합니다." },
    rep_hinge: { after: "A반 평균이 높았던 것은 만점 3명이 평균을 끌어올렸기 때문입니다. 평균은 아주 큰 값이나 작은 값에 끌려가고, 중앙값은 잘 흔들리지 않습니다. 그래서 '평균으로는, 중앙값으로는'처럼 어떤 수인지 함께 말합니다." },
    concept: { say: "'반은 추첨이 아니라 학생이 스스로 골랐다'는 문장은 한 번 더 짚되 왜 중요한지는 말하지 않습니다." },
    overall_predict: { ask: "전체로 보면 대면반, 나눠 보면 온라인반이 앞섭니다. 같은 자료에서 어떻게 반대 결론이 나올 수 있을까요?", avoid: "학생 의견을 두세 개 듣고 넘어갑니다. 정리하지 않습니다." },
    why_simpson: { ask: "그렇다면 대면반 전체 평균이 컸던 까닭은? 확인 문제에서 골라 봅시다." },
    simpson_hinge: { after: "전체 평균은 가중평균입니다. 온라인반 (90명 × 5점 + 10명 × 13점) ÷ 100명 = 5.8점, 대면반 (10명 × 3점 + 90명 × 11점) ÷ 100명 = 10.2점. 하위권이 대면반에 90명 몰려 있었기 때문입니다. 반을 학생이 스스로 골랐으므로 '효과가 증명되었다'고까지는 말할 수 없습니다." },
    g_resample_run: { ask: "세로선(관찰된 +1.2점)은 분포의 가운데와 끝자락 중 어디에 가까운가요?", after: "이 그림은 우연만으로 생기는 차이의 범위를 보여 줄 뿐, 어느 쪽이라고 정해 주지는 않습니다.", avoid: "'우연이다', '차이가 없다'고 교사가 판정하지 않습니다." },
    g_resample_hinge_card: { after: "가운데 부근은 반이 점수와 무관해도 흔히 나는 차이라는 뜻입니다. 증거가 약한 것과 차이가 없다는 증명은 다른 말입니다. 교사가 먼저 p값을 꺼내지 않습니다." },
    x2_l1_wrapup_card: { say: "학생이 한 줄을 쓰면 응답 두세 개를 읽어 준 뒤 '선생님의 한 줄 열기'를 누릅니다. 수치나 대푯값 이름이 들어간 문장을 하나는 고릅니다." },
    x2d_intro: { ask: "학교 밖에서 돈 내고 하는 공부가 사교육입니다. 전국 중학생이 한 달에 얼마나 쓸지 짐작이 가나요?", avoid: "'평균이 아니라 퍼짐을 본다'는 결론은 말하지 않습니다." },
    x2d_predict: { say: "교사 보드의 요약(최소, 중앙값, 최대)을 봅니다. '우리 반 보면'을 근거로 쓴 학생을 기억해 둡니다.", avoid: "이 시점에 학급 예측을 학생에게 보여 주지 않습니다." },
    x2d_source: { after: "이 조사는 국가데이터처가 교육부와 함께 하는 표본조사입니다. B는 그 조사가 쓰는 방법이고, 우리가 할 일은 이미 나와 있는 결과를 찾는 것이라 C입니다." },
    x2d_fetch: { ask: "중학교 줄에서 가장 큰 숫자가 어느 구간에 있나요? 두 번째는?" },
    x2d_reveal: { after: "평균 표의 평균은 받지 않는 학생도 0원으로 넣고 나눈 값입니다. 초안 ③은 평균 하나를 모두에게 씌운 문장입니다. 40~50만 원 구간은 100명 중 약 8명뿐입니다. 학생이 먼저 찾아 말하게 하고 교사는 확인만 합니다." },
    x2d_evidence: { after: "이 자료는 전국 중학생 표본의 결과입니다. 우리 반이 전국과 꼭 같다고도, 전혀 다르다고도 말할 수 없습니다." },
    x2d_income_card: { after: "소득이 높은 가구의 학생이 사교육비를 많이 쓰는 경향은 보이지만, 이 표만으로 소득이 원인이라고 말할 수는 없습니다." },
    diag_post_intro: { say: "첫 시간과 비슷한 문항입니다. 그때 답을 기억하려 하지 말고 지금 생각대로 고릅니다." },
    x2_exit_card: { say: "두세 명에게 어느 문항이 달라졌는지 짧게 듣습니다. 교사가 정답을 말하지 않습니다." },
  };

  let T = load() || fresh();
  let timer = null;
  let focused = null;
  let modal = null;

  function fresh() {
    return {
      track: null, lesson: 0, idx: 0, follow: false, rangeOn: false, range: [], hold: false, showAnswer: false, showNames: false,
      fold: {}, opened: {}, hidden: [], started: false, gathered: false, viewedBoard: false, viewedProgress: false, guideOn: true, collapsed: false, paused: false, students: [],
    };
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
      sessionStorage.setItem(STORE_KEY, JSON.stringify(T));
    } catch (e) {
      return;
    }
  }
  const $ = (sel, root = document) => root.querySelector(sel);
  function rich(v) {
    return esc(v).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function lesson() {
    return DATA.tracks[T.track].lessons[T.lesson];
  }
  function cards() {
    return lesson().cards;
  }
  function card(i = T.idx) {
    return cards()[i];
  }
  function tfOf(c) {
    return (TF[T.track][T.lesson] || {})[c.id] || {};
  }
  function script(c) {
    return SCRIPT[`${T.track}:${c.id}`] || SCRIPT[c.id] || {};
  }
  function openedSet(c) {
    const k = `${T.lesson}:${c.id}`;
    if (!T.opened[k]) T.opened[k] = [];
    return T.opened[k];
  }
  function selfOpen(c) {
    return (c.prompts || []).some((p) => p.requires_resubmit);
  }

  function hash(s) {
    let h = 0;
    for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return h;
  }
  function pick(pool, si, salt) {
    return pool[(si + hash(salt)) % pool.length];
  }
  function weighted(weights, si, salt) {
    const keys = Object.keys(weights);
    const total = keys.reduce((s, k) => s + weights[k], 0);
    let r = (hash(`${salt}:${si}`) % 1000) / 1000 * total;
    for (const k of keys) {
      r -= weights[k];
      if (r < 0) return k;
    }
    return keys[keys.length - 1];
  }

  function makeAnswer(p, si) {
    const pool = SIM.pools[p.prompt_id];
    if (!pool) return { text: "생각을 적었습니다." };
    if (p.type === "hinge") {
      const choice = weighted(pool.weights, si, p.prompt_id);
      const rs = pool.reasons[choice] || ["이유를 적었습니다."];
      return { choice, text: pick(rs, si, p.prompt_id + choice) };
    }
    if (p.type === "predict_pair") {
      const v = pick(pool, si, p.prompt_id);
      return { nums: { none: v[0], high: v[1] }, text: v[2] };
    }
    if (p.type === "predict") {
      const v = pick(pool, si, p.prompt_id);
      return { text: v[0], resubText: v[1] };
    }
    return { text: pick(pool, si, p.prompt_id) };
  }

  function studentCardDone(st, c) {
    const a = st.answers;
    if (c.kind === "diag" || c.kind === "explain" || c.kind === "connector") return Boolean(st.passed[`${T.lesson}:${c.id}`]);
    for (const p of c.prompts || []) {
      const x = a[p.prompt_id];
      if (!x) return false;
      if (p.requires_resubmit && (c.reveals || []).length && !x.resub) return false;
    }
    return true;
  }

  function tick() {
    if (!T.track || !T.started || T.paused) return;
    const list = cards();
    let changed = false;
    T.students.forEach((st, si) => {
      if (!st.joined) {
        if (Math.random() < 0.45) { st.joined = true; st.pos = 0; st.lesson = T.lesson; changed = true; }
        return;
      }
      if (st.lesson !== T.lesson) { st.lesson = T.lesson; st.pos = 0; }
      if (T.follow && st.pos !== T.idx) { st.pos = T.idx; changed = true; }
      const c = list[st.pos];
      if (!c) return;
      const speed = st.speed;
      if (c.kind === "diag" || c.kind === "explain" || c.kind === "connector") {
        if (!st.passed[`${T.lesson}:${c.id}`] && Math.random() < speed) { st.passed[`${T.lesson}:${c.id}`] = true; changed = true; }
      }
      for (const p of c.prompts || []) {
        const x = st.answers[p.prompt_id];
        if (!x && Math.random() < speed * 0.8) {
          st.answers[p.prompt_id] = { ...makeAnswer(p, si), at: Date.now() };
          changed = true;
        } else if (x && p.requires_resubmit && !x.resub && Math.random() < speed * 0.5) {
          x.resub = x.resubText;
          changed = true;
        }
      }
      if (!T.follow && !T.hold && studentCardDone(st, c) && Math.random() < speed) {
        let next = st.pos + 1;
        if (T.rangeOn && T.range.length) {
          const allowed = T.range.filter((i) => i > st.pos).sort((a, b) => a - b);
          next = allowed.length ? allowed[0] : st.pos;
        }
        if (next < list.length && next !== st.pos) { st.pos = next; changed = true; }
      }
    });
    if (changed) {
      save();
      renderBoard();
      renderNav();
      renderStatus();
      if (modal === "progress") renderProgress();
      renderGuide();
    }
  }

  function initStudents() {
    T.students = SIM.students.map((name, i) => ({
      name, pin: String(1000 + ((i * 7919 + 4271) % 9000)).padStart(4, "0"), joined: false, pos: 0, lesson: 0, answers: {}, passed: {},
      speed: [0.55, 0.4, 0.3, 0.45, 0.25, 0.5, 0.35, 0.6, 0.3, 0.42, 0.2, 0.38][i % 12],
    }));
  }

  function renderStatus() {
    const n = T.students.filter((s) => s.joined).length;
    $("#t-status").innerHTML = `접속 <b>${n}</b> / ${T.students.length}명${T.follow ? ' <span class="pill on">따라오기</span>' : ""}${T.hold ? ' <span class="pill on">고정</span>' : ""}${T.rangeOn ? ` <span class="pill on">범위 ${T.range.length}장</span>` : ""}${T.paused ? ' <span class="pill">일시정지</span>' : ""}`;
    const sets = ["follow", "rangeOn", "hold", "showAnswer"];
    const ids = { follow: "#t-follow", rangeOn: "#t-range", hold: "#t-hold", showAnswer: "#t-answer" };
    sets.forEach((k) => $(ids[k]).classList.toggle("on", Boolean(T[k])));
  }

  function renderNav() {
    const list = cards();
    $("#t-nav").innerHTML = `<div class="nav-title">카드 진행바${T.rangeOn ? '<small>범위: 왼쪽 칸을 눌러 고르기</small>' : ""}</div>` + list
      .map((c, i) => {
        const here = T.students.filter((s) => s.joined && s.pos === i).length;
        const inRange = T.range.includes(i);
        return `<button type="button" class="nav-item ${i === T.idx ? "current" : ""} ${inRange && T.rangeOn ? "in-range" : ""}" data-nav="${i}">${T.rangeOn ? `<span class="rbox" data-rangebox="${i}">${inRange ? "✓" : ""}</span>` : ""}<span class="num">${i + 1}</span><span class="tt">${esc(c.title || "")}</span>${here ? `<span class="here">${here}</span>` : ""}</button>`;
      })
      .join("");
    document.querySelectorAll("[data-nav]").forEach((b) =>
      b.addEventListener("click", (e) => {
        const box = e.target.closest("[data-rangebox]");
        if (box) {
          const i = Number(box.dataset.rangebox);
          T.range = T.range.includes(i) ? T.range.filter((x) => x !== i) : T.range.concat([i]);
          T.students.forEach((s) => { if (s.joined && T.range.length && !T.range.includes(s.pos)) s.pos = Math.min(...T.range); });
          save(); renderNav(); renderStatus(); return;
        }
        goCard(Number(b.dataset.nav));
      }),
    );
  }

  function revealBody(r) {
    let html = "";
    if (r.tool_name) html += R.render(lesson().results[r.key] || null, { countLabel: r.count_label || "학생 수" });
    (r.text || []).forEach((t) => (html += `<p>${rich(t)}</p>`));
    if (r.text_rows) html += R.table(r.text_rows[0], r.text_rows.slice(1));
    if (r.figure) html += `<img src="${r.figure}" alt="${esc(r.figure_alt || "")}">`;
    if (r.note) html += `<p class="muted">${rich(r.note)}</p>`;
    return html;
  }

  function renderCard() {
    const c = card();
    const tf = tfOf(c);
    const op = openedSet(c);
    let html = `<div class="card"><p class="group">${T.idx + 1}번 카드${c.group && c.group !== c.title ? `, ${esc(c.group)}` : ""}</p><h2>${esc(c.title || "")}</h2>`;
    (c.body || []).forEach((b) => (html += `<p>${rich(b)}</p>`));
    if (c.figure) html += `<figure><img src="${c.figure}" alt="${esc(c.figure_alt || "")}"></figure>`;
    if (c.side_panel === "sheet" && lesson().dataset) html += `<details class="sheet-d"><summary>학생이 보는 자료 표 (${lesson().dataset.rows.length}행)</summary>${R.table(lesson().dataset.columns, lesson().dataset.rows.slice(0, 60))}</details>`;
    if (c.kind === "diag") {
      const it = c.item;
      html += `<div class="prompt"><div class="q">${rich(it.question)}</div><ul class="t-choices">${it.choices
        .map((ch) => `<li class="${T.showAnswer && tf.item && tf.item.answer === ch.key ? "correct" : ""}">${esc(ch.key)} ${rich(ch.label)}</li>`)
        .join("")}</ul>${T.showAnswer && tf.item ? `<p class="t-guide">정답 ${esc(tf.item.answer)}${tf.item.reason_answer ? `, 이유 ${esc(tf.item.reason_answer)}` : ""}. 표적 ${esc((tf.item.target || []).join(", "))}</p>` : ""}</div>`;
    }
    if (c.kind === "connector") html += `<p class="muted">학생이 '자료 불러오기'를 누르면 KOSIS 표(27행)가 나타납니다.</p>`;
    (c.prompts || []).forEach((p) => {
      const pt = (tf.prompts || {})[p.prompt_id] || {};
      html += `<div class="prompt"><div class="q">${rich(p.question)}</div>`;
      if (p.choices) {
        html += `<ul class="t-choices">${p.choices.map((ch) => `<li class="${T.showAnswer && pt.answer === ch.key ? "correct" : ""}"><b>${esc(ch.key)}.</b> ${rich(ch.label)}${T.showAnswer && ch.target ? ` <small class="muted">(${esc(ch.target.join(", "))})</small>` : ""}</li>`).join("")}</ul>`;
      }
      html += `<textarea disabled placeholder="${esc(p.placeholder || "")}"></textarea><p class="muted">선생님 화면에서는 입력되지 않습니다. 투사해서 '이 질문에 답합니다'라고 가리킬 때 씁니다.</p>`;
      if (T.showAnswer && pt.observe) html += `<p class="t-guide"><b>관찰 가이드</b> ${esc(pt.observe)}${pt.target ? ` <small>(표적 ${esc(pt.target.join(", "))})</small>` : ""}</p>`;
      html += `</div>`;
    });
    if ((c.reveals || []).length) {
      html += `<div class="reveals">`;
      c.reveals.forEach((r, i) => {
        const open = op.includes(r.key);
        const kind = r.open_before_answer ? "답하기 전에도 학생에게 보이는 자료" : selfOpen(c) ? "학생이 각자 여는 공개(선생님이 눌러도 선생님 화면에만 열림)" : "선생님이 여는 공개(답을 보낸 학생에게만 펼쳐짐)";
        html += open
          ? `<div class="reveal"><span class="tag">${esc(kind)}</span>${revealBody(r)}</div>`
          : `<div class="row"><button type="button" class="reveal-btn" data-treveal="${i}">${esc(r.label)}</button><small class="muted">${esc(kind)}</small></div>`;
      });
      html += `</div>`;
    }
    if (c.footer) html += `<div class="footer-text">${c.footer.map((f) => `<p>${rich(f)}</p>`).join("")}</div>`;
    const sc = script(c);
    if (sc.ask || sc.say || sc.after || sc.avoid) {
      html += `<details class="script" open><summary>교사 대본</summary>${sc.ask ? `<p><b>묻기</b> ${esc(sc.ask)}</p>` : ""}${sc.say ? `<p><b>말하기</b> ${esc(sc.say)}</p>` : ""}${sc.after ? `<p><b>답을 받은 뒤 말하기</b> ${esc(sc.after)}</p>` : ""}${sc.avoid ? `<p><b>하지 않기</b> ${esc(sc.avoid)}</p>` : ""}</details>`;
    }
    html += `</div>`;
    $("#t-card").innerHTML = html;
    document.querySelectorAll("[data-treveal]").forEach((b) =>
      b.addEventListener("click", () => {
        const r = c.reveals[Number(b.dataset.treveal)];
        if (!op.includes(r.key)) op.push(r.key);
        save(); renderCard(); renderGuide();
      }),
    );
  }

  function responsesFor(p) {
    return T.students
      .map((s, si) => ({ s, si, a: s.answers[p.prompt_id] }))
      .filter((x) => x.a && !T.hidden.includes(`${p.prompt_id}:${x.si}`));
  }

  function renderBoard() {
    const c = card();
    const tf = tfOf(c);
    const joined = T.students.filter((s) => s.joined);
    let html = `<div class="board-head"><b>응답 보드</b><span><button type="button" id="b-names" class="${T.showNames ? "on" : ""}">이름 보기</button></span></div>`;
    if (!(c.prompts || []).length) {
      if (c.kind === "diag" || c.kind === "explain" || c.kind === "connector") {
        const passed = joined.filter((s) => s.passed[`${T.lesson}:${c.id}`]).length;
        const here = joined.filter((s) => s.pos === T.idx).length;
        html += `<p class="muted">발문이 없는 카드입니다.${c.kind === "diag" ? " 진단 문항은 저장하면 '지나감'으로 표시되고, 채점 결과는 교사 대시보드의 CSV로 받습니다." : ""}</p><p>이 카드를 지나간 학생 <b>${passed}</b>명, 지금 보는 학생 <b>${here}</b>명</p>`;
      }
      $("#t-board").innerHTML = html;
      bindBoard();
      return;
    }
    (c.prompts || []).forEach((p) => {
      const pt = (tf.prompts || {})[p.prompt_id] || {};
      const rs = responsesFor(p);
      const missing = joined.filter((s) => !s.answers[p.prompt_id]);
      html += `<div class="board-q"><div class="bq-head"><span class="bq-type">${esc({ predict: "예측", predict_pair: "예측", hinge: "확인 문제", evidence: "근거 쓰기", exit: "출구 질문" }[p.type] || "")}</span> ${rs.length}/${joined.length} 제출 <button type="button" class="link" data-missing="${esc(p.prompt_id)}">미제출 ${missing.length}명</button></div>`;
      html += `<div class="missing" id="miss-${esc(p.prompt_id)}" hidden>${missing.map((s) => esc(s.name)).join(", ") || "없음"}</div>`;
      if (p.type === "hinge") {
        const counts = {};
        (p.choices || []).forEach((ch) => (counts[ch.key] = 0));
        rs.forEach((x) => (counts[x.a.choice] = (counts[x.a.choice] || 0) + 1));
        const max = Math.max(1, ...Object.values(counts));
        html += `<div class="bars">${(p.choices || [])
          .map((ch) => {
            const n = counts[ch.key] || 0;
            const pct = rs.length ? Math.round((n / rs.length) * 100) : 0;
            const ok = T.showAnswer && pt.answer === ch.key;
            return `<div class="bar-row ${ok ? "correct" : ""}"><span class="bk">${esc(ch.key)}</span><span class="bar"><span style="width:${(n / max) * 100}%"></span></span><span class="bn">${n}명${pct >= 30 && !ok && T.showAnswer ? " ⚠" : ""}</span></div>`;
          })
          .join("")}</div>`;
        if (T.showAnswer) html += `<p class="t-guide small">정답 ${esc(pt.answer || "")}. 특정 오답이 30%를 넘으면(⚠) 그 오개념을 다시 직면시키는 공개나 반례를 씁니다.</p>`;
      }
      if (p.type === "predict_pair" && rs.length) {
        const vals = (k) => rs.map((x) => Number(x.a.nums[k])).sort((a, b) => a - b);
        const sum = (arr) => `최소 ${arr[0]}, 중앙값 ${arr[Math.floor(arr.length / 2)]}, 최대 ${arr[arr.length - 1]}`;
        html += `<div class="hint"><b>받지 않음</b> ${sum(vals("none"))}명<br><b>70만 원 이상</b> ${sum(vals("high"))}명<p class="muted">실제 자료: 각 27명</p></div>`;
      }
      const resub = p.requires_resubmit && (c.reveals || []).length;
      const fold = T.fold[p.prompt_id];
      if (resub) html += `<div class="row"><button type="button" class="link" data-fold="${esc(p.prompt_id)}">${fold ? "처음 의견 펼치기" : "처음 의견 접기"}</button></div>`;
      if (!fold) {
        html += rs
          .map((x) => `<div class="resp"><span class="who">${T.showNames ? esc(x.s.name) : "익명"}${x.a.choice ? `, ${esc(x.a.choice)}` : ""}</span>${x.a.nums ? `<b>${x.a.nums.none}명, ${x.a.nums.high}명</b> ` : ""}${esc(x.a.text)}<button type="button" class="x" title="보드와 친구 의견에서 숨기기" data-hide="${esc(p.prompt_id)}:${x.si}">×</button></div>`)
          .join("");
      }
      if (resub) {
        const rr = rs.filter((x) => x.a.resub);
        html += `<div class="resub-head">재제출 (생각의 변화) ${rr.length}/${rs.length}</div>` + rr.map((x) => `<div class="resp pair"><span class="who">${T.showNames ? esc(x.s.name) : "익명"}</span><p class="first">처음: ${esc(x.a.text)}</p><p>재제출: ${esc(x.a.resub)}</p></div>`).join("");
      }
      html += `</div>`;
    });
    $("#t-board").innerHTML = html;
    bindBoard();
  }

  function bindBoard() {
    const nb = $("#b-names");
    if (nb) nb.onclick = () => { T.showNames = !T.showNames; save(); renderBoard(); };
    document.querySelectorAll("[data-missing]").forEach((b) => (b.onclick = () => { const el = document.getElementById(`miss-${b.dataset.missing}`); el.hidden = !el.hidden; }));
    document.querySelectorAll("[data-fold]").forEach((b) => (b.onclick = () => { T.fold[b.dataset.fold] = !T.fold[b.dataset.fold]; save(); renderBoard(); }));
    document.querySelectorAll("[data-hide]").forEach((b) => (b.onclick = () => { T.hidden.push(b.dataset.hide); save(); renderBoard(); }));
    if (!T.viewedBoard && (card().prompts || []).length) { T.viewedBoard = true; save(); }
  }

  function renderProgress() {
    const list = cards();
    const joined = T.students.filter((s) => s.joined);
    const cell = (s, c, i) => {
      const here = s.pos === i;
      let cls = "";
      let txt = "";
      if ((c.prompts || []).length) {
        const ans = (c.prompts || []).map((p) => s.answers[p.prompt_id]).filter(Boolean);
        if (ans.length === c.prompts.length) { cls = "done"; txt = ans.some((a) => a.resub) ? "재" : ""; }
        else if (ans.length) cls = "part";
      } else if (s.passed[`${T.lesson}:${c.id}`]) cls = "pass";
      return `<td class="${cls} ${here ? "here" : ""}">${txt}</td>`;
    };
    const body = `<h2>학생 진행</h2><p class="muted">${esc(TRACK_LABEL[T.track])}, ${T.lesson + 1}차시. 진한 칸은 제출 완료, 옅은 칸은 지나감, 테두리는 지금 보는 카드, '재'는 재제출까지 보낸 칸입니다.</p>
      <div class="scroll"><table class="grid"><thead><tr><th>학생 ${joined.length}명</th>${list.map((c, i) => `<th title="${esc(c.title || "")}">${i + 1}</th>`).join("")}</tr></thead><tbody>${joined
      .map((s) => `<tr><td>${esc(s.name)}</td>${list.map((c, i) => cell(s, c, i)).join("")}</tr>`)
      .join("")}</tbody></table></div><div class="row"><button type="button" id="m-close">닫기</button></div>`;
    showModal(body, "progress");
  }

  function showModal(html, name) {
    modal = name;
    $("#dialog-root").innerHTML = `<div class="backdrop"><div class="dialog wide" role="dialog" aria-modal="true">${html}</div></div>`;
    const cl = $("#m-close");
    if (cl) cl.onclick = closeModal;
    renderGuide();
  }
  function closeModal() {
    modal = null;
    $("#dialog-root").innerHTML = "";
    renderGuide();
  }

  function joinModal() {
    if (!T.started) { T.started = true; save(); }
    showModal(`<div class="join"><p class="muted">학생은 차시 앱 주소에서 아래 학급 코드를 넣고, 명단에서 자기 이름을 고른 뒤 PIN을 입력합니다.</p><div class="code">${JOIN_CODE}</div><p>구글 계정 없이 들어옵니다. 체험판에서는 가상 학생 ${T.students.length}명이 차례로 들어옵니다.</p></div><div class="row"><button type="button" id="m-close" class="primary">닫고 수업 시작</button></div>`, "join");
  }

  function pinModal() {
    showModal(`<h2>학생 PIN</h2><p class="muted">PIN은 평소에는 가려 두었다가 필요한 학생 것만 보여 줍니다. 쪽지로 인쇄해 나눠 줄 수 있습니다.</p><div class="pin-slips">${T.students
      .map((s) => `<div class="slip"><b>${esc(s.name)}</b><span>학급 코드 ${JOIN_CODE}</span><span>PIN <b>${esc(s.pin)}</b></span></div>`)
      .join("")}</div><div class="row"><button type="button" id="m-print">쪽지 인쇄</button><button type="button" id="m-close" class="primary">닫기</button></div>`, "pin");
    $("#m-print").onclick = () => window.print();
  }

  function settingsModal() {
    const total = Object.values(T.opened).reduce((n, a) => n + a.length, 0);
    showModal(`<h2>설정</h2>
      <p><b>${esc(TRACK_LABEL[T.track])}, ${T.lesson + 1}차시</b></p>
      <div class="row"><select id="m-track">${Object.keys(TRACK_LABEL).map((k) => `<option value="${k}" ${k === T.track ? "selected" : ""}>${TRACK_LABEL[k]}</option>`).join("")}</select><select id="m-lesson"><option value="0" ${T.lesson === 0 ? "selected" : ""}>1차시</option><option value="1" ${T.lesson === 1 ? "selected" : ""}>2차시</option></select><button type="button" id="m-switch">바꾸기</button></div>
      <p>이 학급에 켜진 공개 ${total}개</p><div class="row"><button type="button" id="m-offall">켜진 공개 모두 끄기</button></div>
      <p class="muted">지난 수업이나 리허설에서 연 공개가 남아 있으면 학생 화면에 결과가 처음부터 펼쳐집니다. 수업 10분 전에 모두 끕니다.</p>
      <div class="row"><button type="button" id="m-pause">${T.paused ? "가상 학생 다시 움직이기" : "가상 학생 잠시 멈추기"}</button><button type="button" id="m-reset">가상 학급 처음부터</button><button type="button" id="m-close" class="primary">닫기</button></div>`, "settings");
    $("#m-offall").onclick = () => { T.opened = {}; save(); closeModal(); renderCard(); };
    $("#m-pause").onclick = () => { T.paused = !T.paused; save(); closeModal(); renderStatus(); };
    $("#m-reset").onclick = () => { const tr = T.track; T = { ...fresh(), track: tr, guideOn: T.guideOn }; initStudents(); save(); closeModal(); renderAll(); };
    $("#m-switch").onclick = () => {
      const tr = $("#m-track").value;
      const ls = Number($("#m-lesson").value);
      if (tr !== T.track) { T = { ...fresh(), track: tr, guideOn: T.guideOn }; initStudents(); }
      T.lesson = ls; T.idx = 0; T.range = []; T.rangeOn = false; T.follow = false; T.hold = false;
      T.students.forEach((s) => { s.pos = 0; s.lesson = ls; });
      save(); closeModal(); renderAll();
    };
  }

  function goCard(i) {
    if (i < 0 || i >= cards().length) return;
    T.idx = i;
    save();
    renderAll();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderAll() {
    $("#track-label").textContent = `${TRACK_LABEL[T.track]}, ${T.lesson + 1}차시: ${lesson().title}`;
    renderStatus();
    renderNav();
    renderCard();
    renderBoard();
    $("#t-prev").disabled = T.idx === 0;
    $("#t-next").disabled = T.idx === cards().length - 1;
    renderGuide();
  }

  function guideTask() {
    const c = card();
    const sc = script(c);
    const joined = T.students.filter((s) => s.joined).length;
    const tf = tfOf(c);
    const op = openedSet(c);
    const items = [];
    if (!T.started) return { title: "학생 들어오게 하기", message: "'참여 안내'를 눌러 학급 코드를 크게 띄웁니다. 가상 학생 12명이 차례로 들어옵니다.", target: "#t-join" };
    if (!T.gathered && joined >= 6) return { title: "학생 화면 모으기", message: "'모으기'를 누르면 학생 화면이 지금 카드로 한 번 모입니다. 그 뒤로는 학생이 자유롭게 움직입니다.", items: ["계속 함께 넘기려면 '따라오기'를 켭니다. 따라오기와 범위는 한 쌍이라 하나를 켜면 다른 하나가 꺼집니다."], target: "#t-gather" };
    if (c.kind === "diag") return { title: "진단 문항 진행", message: "진단 문항 동안은 따라오기를 끄고 학생이 각자 넘기게 합니다. '진행 현황'에서 대부분이 체험 카드에 오면 모으기로 함께 시작합니다.", items: [sc.say || "", T.showAnswer ? "" : "'정답'을 켜면 이 문항의 정답과 표적이 보입니다. 화면을 투사 중이면 끕니다."].filter(Boolean), target: T.viewedProgress ? "#t-next" : "#t-progress" };
    if ((c.prompts || []).length) {
      const answered = T.students.filter((s) => s.joined && (c.prompts || []).every((p) => s.answers[p.prompt_id])).length;
      const teacherReveal = (c.reveals || []).find((r) => !r.open_before_answer && !selfOpen(c) && !op.includes(r.key));
      if (!T.showAnswer) items.push("'정답'을 켜면 정답과 관찰 가이드가 보입니다. 투사 중에는 끕니다.");
      if (answered < Math.ceil(joined * 0.6)) {
        return { title: "응답 모으기", message: `학생 답이 오른쪽 응답 보드에 쌓입니다(${answered}/${joined}). 근거의 종류와 오답 보기의 분포를 봅니다.`, items: [sc.ask ? `묻기: ${sc.ask}` : "", sc.avoid ? `하지 않기: ${sc.avoid}` : "", ...items].filter(Boolean), target: T.showAnswer ? "#t-board" : "#t-answer" };
      }
      if (teacherReveal) return { title: "공개 열기", message: `답이 충분히 모였습니다. '${teacherReveal.label}'을 엽니다. 답을 보낸 학생에게만 펼쳐지므로 모두 쓰기를 기다리지 않아도 됩니다.`, items, target: `[data-treveal="${c.reveals.indexOf(teacherReveal)}"]` };
      return { title: "정리하고 넘어가기", message: selfOpen(c) ? "이 카드의 결과는 학생이 각자 엽니다. 재제출이 들어오면 '처음 의견 접기'로 생각의 변화만 남겨 봅니다." : "응답을 두세 개 읽어 주고 정리한 뒤 다음 카드로 넘어갑니다.", items: [sc.after ? `말하기: ${sc.after}` : sc.ask ? `묻기: ${sc.ask}` : "", ...items].filter(Boolean), target: "#t-next" };
    }
    return { title: c.title || "다음 카드", message: "학생과 함께 카드를 읽고 다음으로 넘어갑니다.", items: [sc.say ? `말하기: ${sc.say}` : "", sc.ask ? `묻기: ${sc.ask}` : "", sc.avoid ? `하지 않기: ${sc.avoid}` : ""].filter(Boolean), target: "#t-next" };
  }

  function milestones() {
    const anyOpened = Object.values(T.opened).some((a) => a.length);
    return [["학생 입장", T.started], ["모으기", T.gathered], ["응답 보기", T.viewedBoard], ["정답 확인", T.showAnswer], ["공개 열기", anyOpened], ["진행 현황", T.viewedProgress]];
  }

  function renderGuide() {
    const g = $("#guide");
    if (focused) focused.classList.remove("focus");
    focused = null;
    const visible = T.guideOn && T.track && !$(".backdrop");
    $("#guide-toggle").textContent = T.guideOn ? "안내 끄기" : "안내 켜기";
    if (!visible) { g.hidden = true; return; }
    const task = guideTask();
    const key = `${T.idx}:${task.title}`;
    const prev = g.dataset.key;
    g.hidden = false;
    g.className = `guide${T.collapsed ? " collapsed" : ""}`;
    g.innerHTML = `<div class="guide-head"><span class="eyebrow">교사 체험 안내  ${T.lesson + 1}차시 ${T.idx + 1}/${cards().length}</span><span><button type="button" id="g-col">${T.collapsed ? "펼치기" : "접기"}</button> <button type="button" id="g-off">끄기</button></span></div>
      <div class="guide-body"><h3>${esc(task.title)}</h3><p>${esc(task.message)}</p>${(task.items || []).length ? `<ul>${task.items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}<ul class="milestones">${milestones().map(([l, d]) => `<li class="${d ? "done" : ""}">${esc(l)}</li>`).join("")}</ul></div>`;
    g.dataset.key = key;
    if (prev && prev !== key) { g.classList.remove("guide-flash"); void g.offsetWidth; g.classList.add("guide-flash"); }
    $("#g-col").onclick = () => { T.collapsed = !T.collapsed; save(); renderGuide(); };
    $("#g-off").onclick = () => { T.guideOn = false; save(); renderGuide(); };
    const el = task.target ? document.querySelector(task.target) : null;
    if (el && !T.collapsed) { el.classList.add("focus"); focused = el; }
  }

  function welcome() {
    showModal(`<h2>교사 화면 체험판</h2>
      <p>실험수업(2차시)을 진행하는 교사 진행 화면을 옮겼습니다. 가상 학생 12명이 정해진 속도로 들어와 답을 보내며, 그 답은 체험용으로 만든 글입니다. 실제 학생의 응답은 들어 있지 않습니다.</p>
      <ol>
        <li><b>참여 안내</b>로 학급 코드를 띄우면 학생이 들어옵니다.</li>
        <li><b>모으기, 따라오기, 범위, 고정</b>으로 학생 화면을 움직입니다.</li>
        <li>오른쪽 <b>응답 보드</b>에 답이 쌓이고, <b>정답</b>을 켜면 관찰 가이드가 보입니다.</li>
        <li>카드 아래 <b>교사 대본</b>에 묻는 말, 정리하는 말, 하지 않을 말이 있습니다.</li>
      </ol>
      <div class="track-pick">${Object.keys(TRACK_LABEL).map((k) => `<button type="button" data-ttrack="${k}"><b>${TRACK_LABEL[k]}</b><small>${esc(DATA.tracks[k].lessons[0].title)}</small></button>`).join("")}</div>`, "welcome");
    document.querySelectorAll("[data-ttrack]").forEach((b) =>
      b.addEventListener("click", () => {
        T = { ...fresh(), guideOn: T.guideOn, track: b.dataset.ttrack };
        initStudents();
        save();
        closeModal();
        renderAll();
      }),
    );
  }

  $("#t-gather").addEventListener("click", () => { T.students.forEach((s) => { if (s.joined) s.pos = T.idx; }); T.gathered = true; save(); renderAll(); });
  $("#t-follow").addEventListener("click", () => { T.follow = !T.follow; if (T.follow) { T.rangeOn = false; T.gathered = true; } save(); renderAll(); });
  $("#t-range").addEventListener("click", () => { T.rangeOn = !T.rangeOn; if (T.rangeOn) { T.follow = false; if (!T.range.length) T.range = [T.idx]; } save(); renderAll(); });
  $("#t-hold").addEventListener("click", () => { T.hold = !T.hold; save(); renderAll(); });
  $("#t-answer").addEventListener("click", () => { T.showAnswer = !T.showAnswer; save(); renderAll(); });
  $("#t-progress").addEventListener("click", () => { T.viewedProgress = true; save(); renderProgress(); });
  $("#t-join").addEventListener("click", () => joinModal());
  $("#t-pin").addEventListener("click", () => pinModal());
  $("#t-settings").addEventListener("click", () => settingsModal());
  $("#t-prev").addEventListener("click", () => goCard(T.idx - 1));
  $("#t-next").addEventListener("click", () => goCard(T.idx + 1));
  $("#restart").addEventListener("click", () => welcome());
  $("#guide-toggle").addEventListener("click", () => { T.guideOn = !T.guideOn; T.collapsed = false; save(); renderGuide(); });

  timer = setInterval(tick, 900);
  if (T.track && T.students.length) renderAll();
  else welcome();
})();
