/*
 * NailMap CSV exporter (Phase 1)
 *
 * Usage:
 *   1. Open the NailMap report page while logged in.
 *   2. Wait until the table appears.
 *   3. Open Chrome DevTools -> Console.
 *   4. Paste this whole file and press Enter.
 *
 * What this version improves:
 *   - Always starts from the top of the virtual/infinite-scroll table.
 *   - Repeatedly collects rows while scrolling until the table stops changing.
 *   - Prefers stable row IDs / aria-rowindex / record links for de-duplication.
 *   - Falls back to row contents only when the page exposes no stable identity.
 *   - Reads common "X of Y loaded" / "Showing X-Y of Z" totals.
 *   - Refuses to silently claim success when expected total != exported total.
 *   - Stores the last run in window.__NAILMAP_EXPORT_RESULT__ for debugging.
 *
 * It only reads the current page DOM and downloads a CSV locally.
 */
(async () => {
  const CONFIG = {
    stepRatio: 0.72,
    minStepPx: 320,
    settleMs: 300,
    mutationWaitMs: 900,
    maxIterations: 5000,
    maxStagnantRounds: 12,
    bottomConfirmRounds: 5,
    strictCountCheck: true,
  };

  const logPrefix = "[NailMap CSV]";
  const info = (...args) => console.info(logPrefix, ...args);
  const warn = (...args) => console.warn(logPrefix, ...args);
  const fail = (...args) => console.error(logPrefix, ...args);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const visible = (element) => {
    if (!(element instanceof Element)) return false;
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
  };

  const normalizeText = (value) => String(value ?? "")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  const cellValue = (cell) => {
    const control = cell.querySelector("input, textarea, select");
    if (control) {
      if (control.type === "checkbox" || control.type === "radio") {
        return control.checked ? "YES" : "";
      }
      return normalizeText(control.value);
    }
    return normalizeText(cell.innerText ?? cell.textContent ?? "");
  };

  const rowValues = (row) => [...row.cells].map(cellValue);

  const visibleTables = [...document.querySelectorAll("table")]
    .filter(visible)
    .map((table) => ({
      table,
      visibleRows: [...table.querySelectorAll("tr")].filter(visible).length,
      cellCount: [...table.querySelectorAll("tr")].reduce((sum, row) => sum + row.cells.length, 0),
    }))
    .sort((a, b) => (b.visibleRows - a.visibleRows) || (b.cellCount - a.cellCount));

  const table = visibleTables[0]?.table;
  if (!table) {
    window.alert("Không tìm thấy bảng NailMap đang hiển thị. Hãy chờ bảng tải xong rồi chạy lại script.");
    return;
  }

  const headerCandidates = table.tHead?.rows.length
    ? [...table.tHead.rows]
    : [...table.rows].slice(0, Math.min(3, table.rows.length));
  const headerRow = headerCandidates
    .filter((row) => row.cells.length > 0)
    .sort((a, b) => b.cells.length - a.cells.length)[0];

  const headers = headerRow ? rowValues(headerRow) : [];
  if (!headers.length) {
    window.alert("Không đọc được dòng tiêu đề của bảng.");
    return;
  }

  const normalizedHeaders = headers.map((value, index) => value || `column_${index + 1}`);
  const headerSignature = normalizedHeaders.join("\u001f");

  const scrollableAncestor = (element) => {
    const candidates = [];
    for (let node = element.parentElement; node && node !== document.body; node = node.parentElement) {
      if (!visible(node) || node.clientHeight <= 80) continue;
      const style = window.getComputedStyle(node);
      const overflowY = style.overflowY;
      const canScroll = node.scrollHeight > node.clientHeight + 10;
      candidates.push({ node, canScroll, explicit: overflowY === "auto" || overflowY === "scroll" });
    }
    return candidates.find((item) => item.explicit && item.canScroll)?.node
      || candidates.find((item) => item.canScroll)?.node
      || document.scrollingElement
      || document.documentElement;
  };

  const scroller = scrollableAncestor(table);
  const isDocumentScroller = scroller === document.scrollingElement
    || scroller === document.documentElement
    || scroller === document.body;

  const getScrollTop = () => isDocumentScroller ? window.scrollY : scroller.scrollTop;
  const getClientHeight = () => isDocumentScroller ? window.innerHeight : scroller.clientHeight;
  const getScrollHeight = () => isDocumentScroller
    ? Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)
    : scroller.scrollHeight;
  const setScrollTop = (value) => {
    const safeValue = Math.max(0, Number(value) || 0);
    if (isDocumentScroller) {
      window.scrollTo({ top: safeValue, behavior: "auto" });
    } else {
      scroller.scrollTop = safeValue;
      scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
    }
  };

  const pageText = () => normalizeText(document.body.innerText || document.body.textContent || "");

  const readExpectedTotal = () => {
    const text = pageText();
    const patterns = [
      /([\d,]+)\s+of\s+([\d,]+)\s+loaded/i,
      /showing\s+[\d,]+\s*(?:-|–|to)\s*[\d,]+\s+of\s+([\d,]+)/i,
      /([\d,]+)\s+results?\b/i,
      /total\s*[:=]?\s*([\d,]+)\b/i,
    ];

    const loadedMatch = text.match(patterns[0]);
    if (loadedMatch) {
      return {
        expected: Number(loadedMatch[2].replace(/,/g, "")),
        loaded: Number(loadedMatch[1].replace(/,/g, "")),
        source: loadedMatch[0],
      };
    }

    for (const pattern of patterns.slice(1)) {
      const match = text.match(pattern);
      if (!match) continue;
      const raw = match[1] ?? match[2];
      return {
        expected: Number(String(raw).replace(/,/g, "")),
        loaded: null,
        source: match[0],
      };
    }
    return { expected: null, loaded: null, source: "" };
  };

  const rowIdentity = (row, values) => {
    const attributeNames = [
      "data-row-key",
      "data-row-id",
      "data-id",
      "data-key",
      "data-index",
      "aria-rowindex",
    ];

    for (const name of attributeNames) {
      const value = normalizeText(row.getAttribute(name));
      if (value) return `attr:${name}:${value}`;
    }

    if (row.id) return `id:${row.id}`;

    const usefulLink = [...row.querySelectorAll("a[href]")]
      .map((anchor) => anchor.href)
      .find((href) => /(?:salon|business|shop|location|report|detail|id=|uuid=)/i.test(href));
    if (usefulLink) return `href:${usefulLink}`;

    const dataIdentity = [...row.attributes]
      .filter((attribute) => attribute.name.startsWith("data-") && normalizeText(attribute.value))
      .map((attribute) => `${attribute.name}=${normalizeText(attribute.value)}`)
      .sort()
      .join("|");
    if (dataIdentity) return `data:${dataIdentity}`;

    return `content:${values.join("\u001f")}`;
  };

  const collected = new Map();
  let visibleRowSightings = 0;
  let fallbackIdentityCount = 0;

  const currentDataRows = () => {
    if (table.tBodies.length) {
      return [...table.tBodies].flatMap((body) => [...body.rows]).filter(visible);
    }
    return [...table.rows].filter((row) => row !== headerRow && visible(row));
  };

  const collectCurrentRows = () => {
    let added = 0;
    for (const originalRow of currentDataRows()) {
      let values = rowValues(originalRow).slice(0, normalizedHeaders.length);
      while (values.length < normalizedHeaders.length) values.push("");
      if (!values.some(Boolean)) continue;
      if (values.join("\u001f") === headerSignature) continue;

      visibleRowSightings += 1;
      const key = rowIdentity(originalRow, values);
      if (key.startsWith("content:")) fallbackIdentityCount += 1;
      if (!collected.has(key)) {
        collected.set(key, values);
        added += 1;
      } else {
        collected.set(key, values);
      }
    }
    return added;
  };

  const waitForTableMutation = (timeoutMs) => new Promise((resolve) => {
    let settled = false;
    const finish = (changed) => {
      if (settled) return;
      settled = true;
      observer.disconnect();
      clearTimeout(timer);
      resolve(changed);
    };
    const observer = new MutationObserver(() => finish(true));
    observer.observe(table, { subtree: true, childList: true, characterData: true, attributes: true });
    const timer = setTimeout(() => finish(false), timeoutMs);
  });

  const settleAfterScroll = async () => {
    await Promise.race([waitForTableMutation(CONFIG.mutationWaitMs), sleep(CONFIG.settleMs)]);
    await sleep(80);
  };

  const collectAll = async () => {
    info("Bắt đầu thu thập. Đang đưa bảng về đầu danh sách...");
    setScrollTop(0);
    await settleAfterScroll();
    collectCurrentRows();

    let stagnantRounds = 0;
    let bottomRounds = 0;
    let previousSignature = "";

    for (let iteration = 1; iteration <= CONFIG.maxIterations; iteration += 1) {
      const beforeCount = collected.size;
      const totalInfo = readExpectedTotal();

      if (totalInfo.expected && collected.size >= totalInfo.expected) {
        info(`Đã thu đủ ${collected.size}/${totalInfo.expected} dòng theo bộ đếm trên trang.`);
        break;
      }

      const clientHeight = Math.max(1, getClientHeight());
      const scrollHeight = Math.max(clientHeight, getScrollHeight());
      const maxScrollTop = Math.max(0, scrollHeight - clientHeight);
      const currentTop = getScrollTop();
      const step = Math.max(CONFIG.minStepPx, Math.floor(clientHeight * CONFIG.stepRatio));
      const nextTop = Math.min(maxScrollTop, currentTop + step);

      if (nextTop === currentTop && currentTop < maxScrollTop) {
        setScrollTop(maxScrollTop);
      } else {
        setScrollTop(nextTop);
      }

      await settleAfterScroll();
      collectCurrentRows();

      const afterInfo = readExpectedTotal();
      const afterTop = getScrollTop();
      const afterHeight = getScrollHeight();
      const atBottom = afterTop >= Math.max(0, afterHeight - getClientHeight() - 8);
      const signature = `${Math.round(afterTop)}|${afterHeight}|${afterInfo.loaded ?? ""}|${collected.size}`;
      const noGrowth = collected.size === beforeCount;

      if (signature === previousSignature || noGrowth) stagnantRounds += 1;
      else stagnantRounds = 0;
      previousSignature = signature;

      if (atBottom) bottomRounds += 1;
      else bottomRounds = 0;

      if (iteration === 1 || iteration % 10 === 0 || collected.size !== beforeCount) {
        const expectedText = afterInfo.expected ? `/${afterInfo.expected}` : "";
        const loadedText = afterInfo.loaded != null ? `; NailMap loaded ${afterInfo.loaded}/${afterInfo.expected}` : "";
        info(`Đã thu ${collected.size}${expectedText} dòng${loadedText}; scroll=${Math.round(afterTop)}/${Math.max(0, Math.round(afterHeight - getClientHeight()))}`);
      }

      if (afterInfo.expected && collected.size >= afterInfo.expected) break;

      if (atBottom && bottomRounds <= CONFIG.bottomConfirmRounds) {
        setScrollTop(Math.max(0, getScrollHeight() - getClientHeight()));
        await sleep(CONFIG.settleMs * 2);
        collectCurrentRows();
      }

      if (stagnantRounds >= CONFIG.maxStagnantRounds && bottomRounds >= CONFIG.bottomConfirmRounds) {
        warn("Bảng không thay đổi thêm sau nhiều lần kiểm tra ở cuối danh sách.");
        break;
      }
    }

    setScrollTop(0);
    await settleAfterScroll();
    collectCurrentRows();
    setScrollTop(Math.max(0, getScrollHeight() - getClientHeight()));
    await settleAfterScroll();
    collectCurrentRows();

    return [...collected.values()];
  };

  const csvCell = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;

  const makeExport = (rawRows) => {
    const keepIndexes = normalizedHeaders
      .map((header, index) => header !== `column_${index + 1}` || rawRows.some((row) => normalizeText(row[index])))
      .map((keep, index) => keep ? index : -1)
      .filter((index) => index >= 0);

    const state = new URLSearchParams(window.location.search).get("state")?.toUpperCase() || "ALL";
    const finalHeaders = keepIndexes.map((index) => normalizedHeaders[index]);
    const addStateColumn = state !== "ALL" && !finalHeaders.some((header) => header.toLowerCase() === "state");
    const outputHeaders = addStateColumn ? ["State", ...finalHeaders] : finalHeaders;
    const rows = rawRows.map((row) => {
      const values = keepIndexes.map((index) => row[index] ?? "");
      if (addStateColumn) values.unshift(state);
      return values;
    });

    return { state, outputHeaders, rows };
  };

  const downloadCsv = ({ state, outputHeaders, rows }) => {
    const csv = "\ufeff" + [outputHeaders, ...rows]
      .map((row) => row.map(csvCell).join(","))
      .join("\r\n");
    const filename = `nail-map-${state}-${new Date().toISOString().slice(0, 10)}.csv`;
    const blobUrl = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
    return filename;
  };

  try {
    const rawRows = await collectAll();
    const exportData = makeExport(rawRows);
    const totalInfo = readExpectedTotal();
    const expected = totalInfo.expected;
    const actual = exportData.rows.length;
    const complete = !expected || actual === expected;

    const result = {
      ok: complete,
      complete,
      state: exportData.state,
      expectedRows: expected,
      exportedRows: actual,
      pageCounterText: totalInfo.source,
      fallbackIdentityCount,
      visibleRowSightings,
      headers: exportData.outputHeaders,
      rows: exportData.rows,
      generatedAt: new Date().toISOString(),
    };
    window.__NAILMAP_EXPORT_RESULT__ = result;

    console.table({
      state: result.state,
      expected_rows: expected ?? "unknown",
      exported_rows: actual,
      count_match: expected ? (complete ? "YES" : "NO") : "UNKNOWN",
      fallback_identity_sightings: fallbackIdentityCount,
    });

    if (!actual) {
      throw new Error("Không thu được dòng dữ liệu nào từ bảng.");
    }

    if (!complete && CONFIG.strictCountCheck) {
      const message = [
        `CSV CHƯA ĐƯỢC TẢI vì số dòng chưa khớp.`,
        `NailMap expected: ${expected}`,
        `Tool collected: ${actual}`,
        "",
        "Hãy chờ bảng tải xong và chạy lại script.",
        "Kết quả debug vẫn nằm ở window.__NAILMAP_EXPORT_RESULT__.",
      ].join("\n");
      warn(message);
      window.alert(message);
      return;
    }

    const filename = downloadCsv(exportData);
    result.filename = filename;
    result.ok = true;
    info(`Hoàn tất: ${filename} (${actual} dòng${expected ? ` / expected ${expected}` : ""}).`);
    window.alert(`Export thành công ${actual}${expected ? `/${expected}` : ""} dòng.\n${filename}`);
  } catch (error) {
    fail("Không thể export bảng:", error);
    window.__NAILMAP_EXPORT_RESULT__ = {
      ok: false,
      error: String(error?.message || error),
      generatedAt: new Date().toISOString(),
    };
    window.alert(`Không thể export bảng: ${error?.message || error}`);
  }
})();
