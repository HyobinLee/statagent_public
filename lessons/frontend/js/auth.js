(function () {
  const firebaseSdk = {
    app: "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js",
    auth: "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js",
    firestore: "https://www.gstatic.com/firebasejs/10.14.1/firebase-firestore.js",
  };
  const NAV_ROLE_CACHE_KEY = "lesson-nav-role-cache";
  const ADMIN_ACT_AS_KEY = "stat-agent-admin-act-as-user";
  const ADMIN_ACT_AS_ROLE_KEY = "stat-agent-admin-act-as-role";
  const STUDENT_PREVIEW_KEY = "stat-agent-student-preview";
  const roleLabels = {
    admin: "관리자",
    teacher: "교사",
    student: "학생",
  };
  const state = {
    mode: "dev",
    firebaseReady: false,
    firebaseUser: null,
    app: null,
    auth: null,
    provider: null,
    userProfile: null,
    authError: null,
    firestoreDb: null,
    firestoreModule: null,
  };

  async function fetchClientConfig() {
    return StatApi.request("/api/auth/client-config");
  }

  function currentPageName() {
    return window.location.pathname.split("/").pop() || "index.html";
  }

  function roleHome(role) {
    return {
      admin: "./admin.html",
      teacher: "./teacher.html",
      student: "./index.html",
    }[role] || "./index.html";
  }

  function redirectToRoleHome() {
    window.location.href = roleHome(state.userProfile?.role || StatState.getRole());
  }

  function getAdminActAsUserId() {
    if (currentPageName() === "admin.html") return "";
    return localStorage.getItem(ADMIN_ACT_AS_KEY) || "";
  }

  function getAdminActAsRole() {
    return localStorage.getItem(ADMIN_ACT_AS_ROLE_KEY) || "";
  }

  function clearAdminActAs() {
    localStorage.removeItem(ADMIN_ACT_AS_KEY);
    localStorage.removeItem(ADMIN_ACT_AS_ROLE_KEY);
  }

  function setAdminActAs(userId, role) {
    localStorage.removeItem(STUDENT_PREVIEW_KEY);
    localStorage.setItem(ADMIN_ACT_AS_KEY, userId);
    localStorage.setItem(ADMIN_ACT_AS_ROLE_KEY, role);
    window.location.href = roleHome(role);
  }

  function hasStudentPreviewParam() {
    return new URLSearchParams(window.location.search).get("preview") === "student";
  }

  function isStudentPreview() {
    if (getAdminActAsUserId()) return false;
    return localStorage.getItem(STUDENT_PREVIEW_KEY) === "true" || hasStudentPreviewParam();
  }

  function startStudentPreview() {
    clearAdminActAs();
    localStorage.setItem(STUDENT_PREVIEW_KEY, "true");
    window.location.href = "./lesson1.html?preview=student";
  }

  function clearStudentPreview() {
    localStorage.removeItem(STUDENT_PREVIEW_KEY);
  }

  function getNavRole() {
    if (getAdminActAsUserId()) return getAdminActAsRole() || "student";
    return state.userProfile?.role || StatState.getRole();
  }

  function maybeAutoPreviewForTeacher() {
    if (currentPageName() !== "index.html") return;
    if (isStudentPreview() || getAdminActAsUserId()) return;
    if (getNavRole() === "teacher") {
      localStorage.setItem(STUDENT_PREVIEW_KEY, "true");
    }
  }

  function exitDelegatedView() {
    clearStudentPreview();
    clearAdminActAs();
    window.location.href = "./index.html";
  }

  function getEffectiveRole() {
    if (getAdminActAsUserId()) return getAdminActAsRole() || "student";
    if (isStudentPreview()) return "student";
    return state.userProfile?.role || StatState.getRole();
  }

  function renderDev() {
    const label = document.getElementById("current-user");
    const user = StatState.getUser();
    if (label) {
      const context = isStudentPreview()
        ? " · 학생 화면 미리보기"
        : getAdminActAsUserId()
          ? " · 관리자 대리 접근"
          : "";
      label.textContent = `로컬 개발 · ${user.label} · ${user.email}${context}`;
    }
    setDelegationButton(true);
  }

  function setDelegationButton(signedIn) {
    document.querySelectorAll("[data-delegation-action]").forEach((node) => node.remove());
    if (!signedIn || (!isStudentPreview() && !getAdminActAsUserId())) return;
    const strip = document.querySelector(".user-strip");
    if (!strip) return;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.delegationAction = "exit";
    button.textContent = "차시 목록으로 돌아가기";
    button.addEventListener("click", exitDelegatedView);
    strip.appendChild(button);
  }

  function setAuthControls(text, signedIn) {
    const label = document.getElementById("current-user");
    if (label) {
      label.textContent = text;
    }
    document.querySelectorAll("[data-auth-action]").forEach((node) => node.remove());
    setDelegationButton(signedIn);
    const strip = document.querySelector(".user-strip");
    if (!strip) return;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.authAction = signedIn ? "logout" : "login";
    button.textContent = signedIn ? "로그아웃" : "Google 로그인";
    button.className = signedIn ? "" : "primary";
    button.addEventListener("click", () => {
      if (signedIn) {
        logout().catch((error) => StatApi.toast(error.message));
      } else {
        login().catch((error) => StatApi.toast(error.message));
      }
    });
    strip.appendChild(button);
  }

  function renderFirebaseSignedOut() {
    setAuthControls("로그인이 필요합니다", false);
  }

  async function loadProfile() {
    try {
      state.userProfile = await StatApi.request("/api/auth/me");
      state.authError = null;
    } catch (error) {
      state.userProfile = null;
      state.authError = error.message || "허용된 Google 계정이 아닙니다.";
      return false;
    }
    const role = state.userProfile.role;
    if (role && StatState.users[role]) {
      StatState.setRole(role);
    }
    try {
      localStorage.setItem(NAV_ROLE_CACHE_KEY, role || "");
    } catch (_error) {   }
    return true;
  }

  function getCachedNavRole() {
    try {
      return localStorage.getItem(NAV_ROLE_CACHE_KEY) || "";
    } catch (_error) {
      return "";
    }
  }

  function clearCachedNavRole() {
    try {
      localStorage.removeItem(NAV_ROLE_CACHE_KEY);
    } catch (_error) {   }
  }

  function renderFirebaseSignedIn() {
    const email = state.firebaseUser?.email || state.userProfile?.email || "로그인 사용자";
    const role = state.userProfile?.role || "미등록";
    const displayName = state.userProfile?.display_name || state.firebaseUser?.displayName || email;
    const context = isStudentPreview()
      ? " · 학생 화면 미리보기"
      : getAdminActAsUserId()
        ? " · 관리자 대리 접근"
        : "";
    setAuthControls(`로그인됨 · ${displayName} · ${email} · ${roleLabels[role] || role}${context}`, true);
  }

  function renderFirebaseUnauthorized() {
    const email = state.firebaseUser?.email || "로그인 사용자";
    setAuthControls(`접근 권한 없음 · ${email}`, true);
  }

  async function setupFirebase(config) {
    state.mode = "firebase";
    if (config.missing_firebase_config.length) {
      renderFirebaseSignedOut();
      throw new Error(`Firebase Web 설정이 비어 있습니다: ${config.missing_firebase_config.join(", ")}`);
    }
    const [{ initializeApp }, authModule] = await Promise.all([
      import(firebaseSdk.app),
      import(firebaseSdk.auth),
    ]);
    const app = initializeApp(config.firebase_config);
    state.app = app;
    state.auth = authModule.getAuth(app);
    state.provider = new authModule.GoogleAuthProvider();
    const workspaceDomain = String(config.google_workspace_domain || "").trim().replace(/^@+/, "");
    if (workspaceDomain) {
      state.provider.setCustomParameters({
        hd: workspaceDomain,
        prompt: "select_account",
      });
    }

    await new Promise((resolve) => {
      authModule.onAuthStateChanged(state.auth, async (user) => {
        state.firebaseUser = user;
        if (user) {
          const authorized = await loadProfile();
          if (authorized) {
            maybeAutoPreviewForTeacher();
            renderFirebaseSignedIn();
          } else {
            clearCachedNavRole();
            renderFirebaseUnauthorized();
          }
        } else {
          state.userProfile = null;
          state.authError = null;
          clearCachedNavRole();
          renderFirebaseSignedOut();
        }
        state.firebaseReady = true;
        window.dispatchEvent(
          new CustomEvent("stat-auth-changed", {
            detail: { user, authorized: isSignedIn(), authError: state.authError },
          }),
        );
        resolve();
      });
    });
  }

  async function init() {
    const config = await fetchClientConfig();
    if (config.dev_auth_enabled) {
      state.mode = "dev";
      await loadProfile().catch(() => {});
      maybeAutoPreviewForTeacher();
      renderDev();
      return;
    }
    await setupFirebase(config);
  }

  async function login() {
    if (!state.auth || !state.provider) {
      throw new Error("Firebase 인증이 아직 준비되지 않았습니다.");
    }
    const { signInWithPopup } = await import(firebaseSdk.auth);
    await signInWithPopup(state.auth, state.provider);
  }

  async function loginWithCustomToken(customToken) {
    if (!state.auth) {
      throw new Error("Firebase 인증이 아직 준비되지 않았습니다.");
    }
    const { signInWithCustomToken } = await import(firebaseSdk.auth);
    await signInWithCustomToken(state.auth, customToken);
  }

  async function logout() {
    if (!state.auth) return;
    clearAdminActAs();
    clearStudentPreview();
    const { signOut } = await import(firebaseSdk.auth);
    await signOut(state.auth);
  }

  async function getIdToken(options = {}) {
    if (!state.firebaseUser) {
      throw new Error("Google 로그인이 필요합니다.");
    }
    if (state.mode === "firebase" && !state.userProfile && !options.allowUnverified) {
      throw new Error(state.authError || "허용된 Google 계정이 아닙니다.");
    }
    return state.firebaseUser.getIdToken();
  }

  function isFirebaseMode() {
    return state.mode === "firebase";
  }

  function isSignedIn() {
    return state.mode === "dev" || Boolean(state.userProfile);
  }

  function isAuthorized() {
    return isSignedIn();
  }

  function getProfile() {
    return state.userProfile;
  }

  function getAuthError() {
    return state.authError;
  }

  async function ensureFirestore() {
    if (state.mode !== "firebase" || !state.app) return null;
    if (state.firestoreDb) return state.firestoreDb;
    const firestoreModule = await import(firebaseSdk.firestore);
    state.firestoreModule = firestoreModule;
    state.firestoreDb = firestoreModule.getFirestore(state.app);
    return state.firestoreDb;
  }

  async function watchFirestoreDoc(collectionName, docId, onNext, onError) {
    try {
      const db = await ensureFirestore();
      if (!db) throw new Error("Firestore를 사용할 수 없습니다(로컬 개발 모드).");
      const { doc, onSnapshot } = state.firestoreModule;
      const ref = doc(db, collectionName, docId);
      return onSnapshot(
        ref,
        (snapshot) => onNext(snapshot.exists() ? snapshot.data() : null),
        (error) => onError(error),
      );
    } catch (error) {
      onError(error);
      return () => {};
    }
  }

  async function watchFirestoreQuery(collectionName, wheres, onNext, onError) {
    try {
      const db = await ensureFirestore();
      if (!db) throw new Error("Firestore를 사용할 수 없습니다(로컬 개발 모드).");
      const { collection, query, where, onSnapshot } = state.firestoreModule;
      const constraints = (wheres || []).map(([field, op, value]) => where(field, op, value));
      const ref = query(collection(db, collectionName), ...constraints);
      return onSnapshot(
        ref,
        (snapshot) => onNext(snapshot.docs.map((docSnap) => docSnap.data())),
        (error) => onError(error),
      );
    } catch (error) {
      onError(error);
      return () => {};
    }
  }

  window.StatAuth = {
    init,
    login,
    loginWithCustomToken,
    logout,
    getIdToken,
    isFirebaseMode,
    isSignedIn,
    isAuthorized,
    getProfile,
    getAuthError,
    roleHome,
    redirectToRoleHome,
    getAdminActAsUserId,
    getAdminActAsRole,
    setAdminActAs,
    clearAdminActAs,
    isStudentPreview,
    startStudentPreview,
    clearStudentPreview,
    getEffectiveRole,
    getNavRole,
    getCachedNavRole,
    watchFirestoreDoc,
    watchFirestoreQuery,
  };
})();
