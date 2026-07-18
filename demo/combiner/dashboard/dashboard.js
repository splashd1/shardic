(() => {
  "use strict";

  const state = {
    phase: 1,
    trustees: new Map(),      // username -> {fingerprint, status}
    vault: null,              // {prime_trustee, pool_trustees, threshold, pool_threshold}
    recovery: null,           // {repliedUsernames: Set, poolThreshold}
    finalized: null,          // {trustees_used, outdir}
    lastVerify: null,         // {match}
    trusteesRequired: 5,
  };

  const $ = (id) => document.getElementById(id);
  const phaseSections = Array.from(document.querySelectorAll(".phase"));
  const phaseRadios = Array.from(document.querySelectorAll('input[name="phase"]'));
  const phaseIndicator = $("phase-indicator");

  function setPhase(n) {
    state.phase = n;
    phaseSections.forEach((el) => el.classList.toggle("is-active", Number(el.dataset.phase) === n));
    phaseRadios.forEach((el) => { el.checked = Number(el.value) === n; });
    phaseIndicator.textContent = `Phase ${n} of 4`;
  }

  phaseRadios.forEach((el) => el.addEventListener("change", () => setPhase(Number(el.value))));
  $("phase-prev").addEventListener("click", () => setPhase(Math.max(1, state.phase - 1)));
  $("phase-next").addEventListener("click", () => setPhase(Math.min(4, state.phase + 1)));

  // --------------------------------------------------------------- logging

  function log(text, isError) {
    const line = document.createElement("div");
    line.className = "ceremony-log__line" + (isError ? " ceremony-log__line--error" : "");
    const time = document.createElement("span");
    time.className = "ceremony-log__time";
    time.textContent = new Date().toLocaleTimeString();
    line.appendChild(time);
    line.appendChild(document.createTextNode(text));
    $("ceremony-log").prepend(line);
  }

  // ------------------------------------------------------------- rendering

  function renderTrustees() {
    const grid = $("trustee-grid");
    grid.innerHTML = "";
    const primeName = state.vault ? state.vault.prime_trustee : null;
    const sorted = Array.from(state.trustees.entries()).sort((a, b) => a[0].localeCompare(b[0]));
    for (const [username, rec] of sorted) {
      const card = document.createElement("div");
      card.className = "trustee-card" + (username === primeName ? " trustee-card--prime" : "");
      const dot = document.createElement("span");
      dot.className = "trustee-dot trustee-dot--" + (rec.status === "paused" ? "paused" : "live");
      const name = document.createElement("span");
      name.className = "trustee-card__name";
      name.textContent = username;
      const fp = document.createElement("span");
      fp.className = "trustee-card__fp";
      fp.textContent = rec.fingerprint ? rec.fingerprint.slice(0, 12) : "";
      card.append(dot, name, fp);
      grid.appendChild(card);
    }
  }

  function renderFormation() {
    const hasVault = !!state.vault;
    $("formation-callout").hidden = !hasVault;
    $("formation-pipeline").hidden = !hasVault;
    if (hasVault) {
      $("formation-prime").textContent = state.vault.prime_trustee;
      $("formation-pool").textContent = state.vault.pool_trustees.join(", ");
      $("formation-split-label").textContent =
        `prime mask + ${state.vault.pool_trustees.length} pool shares (pool threshold ${state.vault.pool_threshold})`;
      $("dormant-prime").textContent = state.vault.prime_trustee;
      $("dormant-pool").textContent = state.vault.pool_trustees.join(", ");
    }
  }

  function renderShardProgress() {
    const primeName = state.vault ? state.vault.prime_trustee : null;
    const replied = state.recovery ? state.recovery.repliedUsernames : new Set();
    $("shard-prime-status").className =
      "shard-dot " + (primeName && replied.has(primeName) ? "shard-dot--received" : "shard-dot--pending");

    const poolThreshold = state.recovery && state.recovery.poolThreshold != null
      ? state.recovery.poolThreshold
      : (state.vault ? state.vault.pool_threshold : "?");
    const poolReplied = Array.from(replied).filter((u) => u !== primeName);
    $("shard-pool-count").textContent = poolReplied.length;
    $("shard-pool-threshold").textContent = poolThreshold;

    const list = $("shard-pool-list");
    list.innerHTML = "";
    for (const username of poolReplied) {
      const chip = document.createElement("span");
      chip.className = "shard-chip";
      chip.textContent = username;
      list.appendChild(chip);
    }
  }

  function renderFinalize() {
    if (state.finalized) {
      $("finalize-trustees").textContent = state.finalized.trustees_used.join(", ");
      $("finalize-outdir").textContent = state.finalized.outdir;
    }
    const banner = $("verify-banner");
    if (state.lastVerify == null) {
      banner.className = "verify-banner verify-banner--pending";
      banner.textContent = "Recovery not yet verified.";
    } else if (state.lastVerify.match) {
      banner.className = "verify-banner verify-banner--match";
      banner.textContent = "MATCH — recovered plaintext is byte-for-byte identical to the original.";
    } else {
      banner.className = "verify-banner verify-banner--mismatch";
      banner.textContent = "MISMATCH — recovered plaintext does not match the original.";
    }
  }

  function renderControls() {
    const registeredCount = state.trustees.size;
    $("btn-create-vault").disabled = !!state.vault || registeredCount < state.trusteesRequired;
    $("btn-start-recovery").disabled = !state.vault;
    $("btn-finalize").disabled = !state.recovery;
    $("btn-verify").disabled = !state.finalized;
  }

  function renderAll() {
    renderTrustees();
    renderFormation();
    renderShardProgress();
    renderFinalize();
    renderControls();
  }

  // ------------------------------------------------------------ SSE wiring

  function applySnapshot(data) {
    state.trusteesRequired = data.trustees_required;
    state.trustees = new Map(data.trustees.map((t) => [t.username, { fingerprint: t.fingerprint, status: t.status }]));
    state.vault = data.vault;
    state.recovery = data.recovery
      ? { repliedUsernames: new Set(data.recovery.replied_usernames), poolThreshold: data.recovery.pool_threshold }
      : null;
    state.lastVerify = data.last_verify;
    // Can't distinguish "finalized" from "in-progress" purely from the
    // snapshot (recovery_session isn't cleared on finalize) -- `finalized`
    // stays unset on reconnect; the Verify button re-enables once Finalize
    // is (re-)clicked or a fresh recovery_finalized event lands.
    let phase = 1;
    if (state.lastVerify) phase = 4;
    else if (state.recovery) phase = 3;
    else if (state.vault) phase = 2;
    setPhase(phase);
    renderAll();
  }

  function connect() {
    const source = new EventSource("/events");
    source.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      handleEvent(msg.type, msg.data);
    };
    source.onerror = () => log("SSE connection lost -- browser will retry automatically.", true);
  }

  function handleEvent(type, data) {
    switch (type) {
      case "snapshot":
        applySnapshot(data);
        log("dashboard connected, state synced");
        return;
      case "trustee_registered":
        state.trustees.set(data.username, { fingerprint: data.fingerprint, status: "live" });
        log(`trustee registered: ${data.username} (${data.fingerprint.slice(0, 12)})`);
        break;
      case "trustee_status": {
        const rec = state.trustees.get(data.username);
        if (rec) rec.status = data.status;
        log(`${data.username} is now ${data.status}`);
        break;
      }
      case "vault_created":
        state.vault = data;
        log(`vault created — prime: ${data.prime_trustee}, pool: ${data.pool_trustees.join(", ")}`);
        setPhase(2);
        break;
      case "recovery_started":
        state.recovery = { repliedUsernames: new Set(), poolThreshold: state.vault ? state.vault.pool_threshold : null };
        state.finalized = null;
        state.lastVerify = null;
        log(`recovery session started (${data.session_id})`);
        setPhase(3);
        break;
      case "shard_received":
        if (state.recovery) {
          state.recovery.repliedUsernames.add(data.username);
          state.recovery.poolThreshold = data.pool_threshold;
        }
        log(`shard received from ${data.username} (${data.replied_count} received so far)`);
        break;
      case "recovery_finalized":
        state.finalized = data;
        log(`recovery finalized — trustees used: ${data.trustees_used.join(", ")}`);
        break;
      case "recovery_verified":
        state.lastVerify = data;
        log(data.match ? "verification: MATCH" : "verification: MISMATCH");
        setPhase(4);
        break;
      default:
        log(`unrecognized event: ${type}`);
    }
    renderAll();
  }

  // ------------------------------------------------------------- controls

  function adminToken() {
    return $("admin-token").value;
  }

  async function callAdmin(path) {
    const res = await fetch(path, { method: "POST", headers: { "X-Admin-Token": adminToken() } });
    let body = {};
    try { body = await res.json(); } catch (_e) { /* no body */ }
    if (!res.ok) {
      log(`${path} failed: ${body.error || res.status}`, true);
      return null;
    }
    return body;
  }

  $("admin-token").value = localStorage.getItem("shardic_admin_token") || "";
  $("admin-token").addEventListener("input", (e) => {
    localStorage.setItem("shardic_admin_token", e.target.value);
  });

  $("btn-create-vault").addEventListener("click", () => callAdmin("/admin/vault/create"));
  $("btn-start-recovery").addEventListener("click", () => callAdmin("/admin/recovery/start"));
  $("btn-finalize").addEventListener("click", async () => {
    const result = await callAdmin("/admin/recovery/finalize");
    if (result) renderControls();
  });
  $("btn-verify").addEventListener("click", () => callAdmin("/admin/recovery/verify"));

  setPhase(1);
  connect();
})();
