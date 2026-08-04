(function (root, factory) {
  const studio = factory(root);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = studio;
  }
  if (root) {
    root.EtherfiStudio = studio;
  }
  if (typeof document !== "undefined") {
    studio.ready(document);
  }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  const DASHBOARD_SELECTOR = "[data-studio-dashboard]";
  const CONFIG_SELECTOR = "script[data-studio-config]";
  const RANGE_OPTIONS = Object.freeze(["7D", "30D", "90D", "YTD", "1Y", "ALL"]);
  const CHART_STYLES = Object.freeze(["line", "area", "column", "scatter"]);
  const RANGE_DAYS = Object.freeze({
    "7D": 7,
    "30D": 30,
    "90D": 90,
    "1Y": 365,
  });
  const COLOR_FALLBACKS = Object.freeze({
    green: "#44c78b",
    blue: "#5b8def",
    coral: "#ef7f72",
    amber: "#d8a444",
  });
  const EMPTY_VALUE = "—";
  const INTELLIGENCE_SOURCE = "kyberswap_depositor_intelligence";
  const EVM_EXPLORERS = Object.freeze({
    arbitrum: { baseUrl: "https://arbiscan.io", label: "Arbiscan" },
    avalanche: { baseUrl: "https://snowtrace.io", label: "Snowtrace" },
    base: { baseUrl: "https://basescan.org", label: "Basescan" },
    bnb: { baseUrl: "https://bscscan.com", label: "BscScan" },
    ethereum: { baseUrl: "https://etherscan.io", label: "Etherscan" },
    linea: { baseUrl: "https://lineascan.build", label: "LineaScan" },
    optimism: { baseUrl: "https://optimistic.etherscan.io", label: "Optimism Explorer" },
    polygon: { baseUrl: "https://polygonscan.com", label: "PolygonScan" },
    scroll: { baseUrl: "https://scrollscan.com", label: "Scrollscan" },
  });
  const STUDIO_MOBILE_BREAKPOINT = 720;
  const RELATIVE_AGE_REFRESH_MS = 60 * 1000;
  const STUDIO_REPOSITORY_FILE_BASE =
    "https://github.com/henrystats/etherfi-data-catalog/blob/main/";
  const ZIP_UTF8_FLAG = 0x0800;
  const textEncoder = typeof TextEncoder !== "undefined" ? new TextEncoder() : null;

  function isNil(value) {
    return value === null || value === undefined || value === "";
  }

  function decimalStringParts(value) {
    if (typeof value !== "string") {
      return null;
    }
    const source = value.trim();
    const match = source.match(
      /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/,
    );
    if (!match) {
      return null;
    }
    const exponent = Number(match[5] || 0);
    if (!Number.isSafeInteger(exponent)) {
      return {
        source,
        negative: match[1] === "-",
        coefficient: "",
        exponent: 0,
        unsafe: true,
      };
    }
    const integer = match[2] || "0";
    const fraction = match[2] !== undefined ? (match[3] || "") : match[4];
    let coefficient = `${integer}${fraction}`.replace(/^0+/, "");
    let decimalExponent = exponent - fraction.length;
    if (!coefficient) {
      return {
        source,
        negative: match[1] === "-",
        coefficient: "0",
        exponent: 0,
        unsafe: false,
      };
    }
    while (coefficient.endsWith("0")) {
      coefficient = coefficient.slice(0, -1);
      decimalExponent += 1;
    }
    return {
      source,
      negative: match[1] === "-",
      coefficient,
      exponent: decimalExponent,
      unsafe: false,
    };
  }

  function decimalPartsEqual(left, right) {
    return Boolean(
      left
      && right
      && left.coefficient === right.coefficient
      && left.exponent === right.exponent
      && (left.coefficient === "0" || left.negative === right.negative),
    );
  }

  function integerCoefficientIsSafe(parts) {
    if (!parts || parts.coefficient === "0" || parts.exponent < 0) {
      return true;
    }
    const digits = `${parts.coefficient}${"0".repeat(parts.exponent)}`;
    const maximum = String(Number.MAX_SAFE_INTEGER);
    return digits.length < maximum.length
      || (digits.length === maximum.length && digits <= maximum);
  }

  function unsafeNumericStringParts(value) {
    const parts = decimalStringParts(value);
    if (!parts) {
      return null;
    }
    const parsed = Number(parts.source);
    if (!Number.isFinite(parsed) || parts.unsafe) {
      return { ...parts, unsafe: true };
    }
    const roundTrip = decimalStringParts(String(parsed));
    const isInteger = parts.exponent >= 0;
    const hasExcessPrecision = !isInteger && (
      parts.coefficient.length > 15
      || -parts.exponent > 15
    );
    return {
      ...parts,
      unsafe: !decimalPartsEqual(parts, roundTrip)
        || !integerCoefficientIsSafe(parts)
        || hasExcessPrecision,
    };
  }

  function finiteNumber(value) {
    if (typeof value === "number") {
      return Number.isFinite(value) ? value : null;
    }
    if (typeof value === "string" && value.trim() !== "") {
      const parts = unsafeNumericStringParts(value);
      if (!parts || parts.unsafe) {
        return null;
      }
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  }

  function parseDate(value) {
    if (value instanceof Date) {
      return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
    }
    if (typeof value !== "string" && typeof value !== "number") {
      return null;
    }
    const source = String(value).trim();
    if (!source) {
      return null;
    }
    const normalized = /^\d{4}-\d{2}-\d{2}$/.test(source)
      ? `${source}T00:00:00Z`
      : source;
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function parseUtcTimestamp(value) {
    if (value instanceof Date) {
      return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
    }
    if (typeof value !== "string" && typeof value !== "number") {
      return null;
    }
    const source = String(value).trim();
    if (!source) {
      return null;
    }
    const normalized = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(source)
      ? `${source.replace(" ", "T")}Z`
      : source;
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function relativeAgeReferenceDate(referenceTime) {
    const explicit = parseUtcTimestamp(referenceTime);
    if (explicit) {
      return explicit;
    }
    const fixed = root && root.__STUDIO_REFERENCE_TIME__;
    return parseUtcTimestamp(fixed) || new Date();
  }

  function relativeAgeLabel(value, referenceTime) {
    const timestamp = parseUtcTimestamp(value);
    if (!timestamp) {
      return String(value || "");
    }
    const reference = relativeAgeReferenceDate(referenceTime);
    const elapsedSeconds = Math.max(
      0,
      Math.floor((reference.getTime() - timestamp.getTime()) / 1000),
    );
    if (elapsedSeconds < 60) {
      return "Just now";
    }
    const minutes = Math.floor(elapsedSeconds / 60);
    if (minutes < 60) {
      return `${minutes} ${minutes === 1 ? "min" : "mins"} ago`;
    }
    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return `${hours} ${hours === 1 ? "hr" : "hrs"} ago`;
    }
    const days = Math.floor(hours / 24);
    if (days < 30) {
      return `${days} ${days === 1 ? "day" : "days"} ago`;
    }
    if (days < 365) {
      const months = Math.floor(days / 30);
      return `${months} ${months === 1 ? "month" : "months"} ago`;
    }
    const years = Math.floor(days / 365);
    return `${years} ${years === 1 ? "year" : "years"} ago`;
  }

  function utcStartOfDay(value) {
    const date = parseDate(value);
    if (!date) {
      return null;
    }
    return new Date(Date.UTC(
      date.getUTCFullYear(),
      date.getUTCMonth(),
      date.getUTCDate(),
    ));
  }

  function latestDate(rows, dateColumn) {
    if (!Array.isArray(rows) || !dateColumn) {
      return null;
    }
    let latest = null;
    rows.forEach((row) => {
      const parsed = parseDate(row && row[dateColumn]);
      if (parsed && (!latest || parsed > latest)) {
        latest = parsed;
      }
    });
    return latest;
  }

  function rangeCutoff(range, latest) {
    const normalizedRange = RANGE_OPTIONS.includes(String(range))
      ? String(range)
      : "ALL";
    if (normalizedRange === "ALL") {
      return null;
    }
    const end = utcStartOfDay(latest);
    if (!end) {
      return null;
    }
    if (normalizedRange === "YTD") {
      return new Date(Date.UTC(end.getUTCFullYear(), 0, 1));
    }
    const dayCount = RANGE_DAYS[normalizedRange];
    if (!dayCount) {
      return null;
    }
    const cutoff = new Date(end.getTime());
    cutoff.setUTCDate(cutoff.getUTCDate() - (dayCount - 1));
    return cutoff;
  }

  function filterRowsByRange(rows, dateColumn, range, referenceDate) {
    const values = Array.isArray(rows) ? rows.slice() : [];
    if (!dateColumn || String(range) === "ALL") {
      return values;
    }
    const endDate = utcStartOfDay(referenceDate || latestDate(values, dateColumn));
    if (!endDate) {
      return [];
    }
    const cutoff = rangeCutoff(range, endDate);
    if (!cutoff) {
      return values;
    }
    const endExclusive = new Date(endDate.getTime());
    endExclusive.setUTCDate(endExclusive.getUTCDate() + 1);
    return values.filter((row) => {
      const parsed = parseDate(row && row[dateColumn]);
      return parsed && parsed >= cutoff && parsed < endExclusive;
    });
  }

  function comparableValue(value) {
    if (value instanceof Date) {
      return { kind: "date", value: value.getTime() };
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return { kind: "decimal", value: decimalStringParts(String(value)) };
    }
    if (typeof value === "boolean") {
      return { kind: "decimal", value: decimalStringParts(value ? "1" : "0") };
    }
    const text = String(value);
    const decimal = decimalStringParts(text);
    if (decimal && decimal.coefficient) {
      return { kind: "decimal", value: decimal };
    }
    if (/^\d{4}-\d{2}-\d{2}(?:T|\s|$)/.test(text)) {
      const date = parseDate(text);
      if (date) {
        return { kind: "date", value: date.getTime() };
      }
    }
    return { kind: "string", value: text };
  }

  function compareDecimalParts(left, right) {
    const leftZero = left.coefficient === "0";
    const rightZero = right.coefficient === "0";
    if (leftZero || rightZero) {
      if (leftZero && rightZero) {
        return 0;
      }
      if (leftZero) {
        return right.negative ? 1 : -1;
      }
      return left.negative ? -1 : 1;
    }
    if (left.negative !== right.negative) {
      return left.negative ? -1 : 1;
    }
    const leftMagnitude = left.coefficient.length + left.exponent;
    const rightMagnitude = right.coefficient.length + right.exponent;
    let compared = 0;
    if (leftMagnitude !== rightMagnitude) {
      compared = leftMagnitude < rightMagnitude ? -1 : 1;
    } else {
      const width = Math.max(left.coefficient.length, right.coefficient.length);
      const leftDigits = left.coefficient.padEnd(width, "0");
      const rightDigits = right.coefficient.padEnd(width, "0");
      compared = leftDigits === rightDigits ? 0 : (leftDigits < rightDigits ? -1 : 1);
    }
    return left.negative ? -compared : compared;
  }

  function compareValues(left, right) {
    const a = comparableValue(left);
    const b = comparableValue(right);
    if (a.kind === "decimal" && b.kind === "decimal") {
      return compareDecimalParts(a.value, b.value);
    }
    if (a.kind === "date" && b.kind === "date") {
      return a.value === b.value ? 0 : (a.value < b.value ? -1 : 1);
    }
    return String(a.value).localeCompare(String(b.value), "en", {
      numeric: true,
      sensitivity: "base",
    });
  }

  function sortRows(rows, column, direction) {
    const multiplier = String(direction).toLowerCase().startsWith("desc") ? -1 : 1;
    return (Array.isArray(rows) ? rows : [])
      .map((row, index) => ({ row, index }))
      .sort((left, right) => {
        const leftValue = left.row && left.row[column];
        const rightValue = right.row && right.row[column];
        const leftMissing = isNil(leftValue);
        const rightMissing = isNil(rightValue);
        if (leftMissing || rightMissing) {
          if (leftMissing && rightMissing) {
            return left.index - right.index;
          }
          return leftMissing ? 1 : -1;
        }
        const compared = compareValues(leftValue, rightValue);
        return compared === 0
          ? left.index - right.index
          : compared * multiplier;
      })
      .map((entry) => entry.row);
  }

  function searchTerms(query) {
    return String(query || "")
      .toLocaleLowerCase("en")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
  }

  function tableSearchText(row, columns, columnFormats, metric) {
    const values = [];
    (Array.isArray(columns) ? columns : []).forEach((column) => {
      const value = row && row[column];
      if (value === null || value === undefined) {
        return;
      }
      values.push(String(value));
      if (metric && identifierKindForColumn(metric, column)) {
        values.push(shortAddress(value));
      }
      const format = columnFormats && columnFormats[column];
      if (format) {
        values.push(formatValue(value, format, metric));
      }
    });
    return values.join(" ").toLocaleLowerCase("en");
  }

  function filterTableRows(rows, columns, query, columnFormats, metric) {
    const source = Array.isArray(rows) ? rows : [];
    const terms = searchTerms(query);
    if (!terms.length) {
      return source.slice();
    }
    return source.filter((row) => {
      const searchable = tableSearchText(row, columns, columnFormats, metric);
      return terms.every((term) => searchable.includes(term));
    });
  }

  function deriveTableView(rows, columns, options) {
    const config = options || {};
    const source = Array.isArray(rows) ? rows : [];
    const filtered = filterTableRows(
      source,
      Array.isArray(config.searchColumns) ? config.searchColumns : columns,
      config.query,
      config.columnFormats,
      config.metric,
    );
    const sorted = config.sortColumn
      ? sortRows(filtered, config.sortColumn, config.sortDirection)
      : filtered.slice();
    const pageSize = Math.max(1, Number(config.pageSize) || 10);
    const pageCount = sorted.length ? Math.ceil(sorted.length / pageSize) : 0;
    const requestedPage = Math.max(0, Number(config.page) || 0);
    const page = pageCount ? Math.min(requestedPage, pageCount - 1) : 0;
    const start = page * pageSize;
    return {
      rows: sorted.slice(start, start + pageSize),
      sortedRows: sorted,
      totalRows: source.length,
      filteredRows: sorted.length,
      page,
      pageCount,
      pageSize,
      start,
      end: Math.min(start + pageSize, sorted.length),
    };
  }

  function csvEscape(value) {
    if (value === null || value === undefined) {
      return "";
    }
    let text;
    if (value instanceof Date) {
      text = value.toISOString();
    } else if (typeof value === "object") {
      text = JSON.stringify(value);
    } else {
      text = String(value);
    }
    if (
      typeof value === "string"
      && /^[\t ]*[=+\-@]/.test(text)
    ) {
      text = `'${text}`;
    }
    if (/[",\r\n]/.test(text) || /^\s|\s$/.test(text)) {
      return `"${text.replace(/"/g, "\"\"")}"`;
    }
    return text;
  }

  function inferredColumns(rows) {
    const columns = [];
    const seen = new Set();
    (Array.isArray(rows) ? rows : []).forEach((row) => {
      if (!row || typeof row !== "object") {
        return;
      }
      Object.keys(row).forEach((column) => {
        if (!seen.has(column)) {
          seen.add(column);
          columns.push(column);
        }
      });
    });
    return columns;
  }

  function buildCsv(rows, columns) {
    const sourceRows = Array.isArray(rows) ? rows : [];
    const selectedColumns = Array.isArray(columns) && columns.length
      ? columns.slice()
      : inferredColumns(sourceRows);
    const lines = [selectedColumns.map(csvEscape).join(",")];
    sourceRows.forEach((row) => {
      lines.push(selectedColumns.map((column) => csvEscape(row && row[column])).join(","));
    });
    return `${lines.join("\r\n")}\r\n`;
  }

  function encodeUtf8(value) {
    const text = String(value);
    if (textEncoder) {
      return textEncoder.encode(text);
    }
    const escaped = unescape(encodeURIComponent(text));
    const bytes = new Uint8Array(escaped.length);
    for (let index = 0; index < escaped.length; index += 1) {
      bytes[index] = escaped.charCodeAt(index);
    }
    return bytes;
  }

  let crcTable = null;

  function getCrcTable() {
    if (crcTable) {
      return crcTable;
    }
    crcTable = new Uint32Array(256);
    for (let index = 0; index < 256; index += 1) {
      let value = index;
      for (let bit = 0; bit < 8; bit += 1) {
        value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
      }
      crcTable[index] = value >>> 0;
    }
    return crcTable;
  }

  function crc32(bytes) {
    const table = getCrcTable();
    let crc = 0xffffffff;
    for (let index = 0; index < bytes.length; index += 1) {
      crc = table[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  function writeUint16(view, offset, value) {
    view.setUint16(offset, value & 0xffff, true);
  }

  function writeUint32(view, offset, value) {
    view.setUint32(offset, value >>> 0, true);
  }

  function concatBytes(parts) {
    const total = parts.reduce((sum, part) => sum + part.length, 0);
    const output = new Uint8Array(total);
    let offset = 0;
    parts.forEach((part) => {
      output.set(part, offset);
      offset += part.length;
    });
    return output;
  }

  function normalizeZipEntries(entries) {
    if (!Array.isArray(entries)) {
      return [];
    }
    return entries.map((entry, index) => {
      const name = entry && entry.name ? String(entry.name) : `file-${index + 1}.txt`;
      let data;
      if (entry && entry.data instanceof Uint8Array) {
        data = entry.data;
      } else if (
        entry &&
        entry.data &&
        entry.data.buffer instanceof ArrayBuffer &&
        typeof entry.data.byteLength === "number"
      ) {
        data = new Uint8Array(
          entry.data.buffer,
          entry.data.byteOffset || 0,
          entry.data.byteLength,
        );
      } else {
        data = encodeUtf8(entry && entry.data !== undefined ? entry.data : "");
      }
      return {
        name: encodeUtf8(name),
        data,
        crc: crc32(data),
      };
    });
  }

  function createZip(entries) {
    const normalized = normalizeZipEntries(entries);
    const localParts = [];
    const centralParts = [];
    let localOffset = 0;

    normalized.forEach((entry) => {
      const local = new Uint8Array(30 + entry.name.length);
      const localView = new DataView(local.buffer);
      writeUint32(localView, 0, 0x04034b50);
      writeUint16(localView, 4, 20);
      writeUint16(localView, 6, ZIP_UTF8_FLAG);
      writeUint16(localView, 8, 0);
      writeUint16(localView, 10, 0);
      writeUint16(localView, 12, 33);
      writeUint32(localView, 14, entry.crc);
      writeUint32(localView, 18, entry.data.length);
      writeUint32(localView, 22, entry.data.length);
      writeUint16(localView, 26, entry.name.length);
      writeUint16(localView, 28, 0);
      local.set(entry.name, 30);
      localParts.push(local, entry.data);

      const central = new Uint8Array(46 + entry.name.length);
      const centralView = new DataView(central.buffer);
      writeUint32(centralView, 0, 0x02014b50);
      writeUint16(centralView, 4, 20);
      writeUint16(centralView, 6, 20);
      writeUint16(centralView, 8, ZIP_UTF8_FLAG);
      writeUint16(centralView, 10, 0);
      writeUint16(centralView, 12, 0);
      writeUint16(centralView, 14, 33);
      writeUint32(centralView, 16, entry.crc);
      writeUint32(centralView, 20, entry.data.length);
      writeUint32(centralView, 24, entry.data.length);
      writeUint16(centralView, 28, entry.name.length);
      writeUint16(centralView, 30, 0);
      writeUint16(centralView, 32, 0);
      writeUint16(centralView, 34, 0);
      writeUint16(centralView, 36, 0);
      writeUint32(centralView, 38, 0);
      writeUint32(centralView, 42, localOffset);
      central.set(entry.name, 46);
      centralParts.push(central);
      localOffset += local.length + entry.data.length;
    });

    const centralDirectory = concatBytes(centralParts);
    const end = new Uint8Array(22);
    const endView = new DataView(end.buffer);
    writeUint32(endView, 0, 0x06054b50);
    writeUint16(endView, 4, 0);
    writeUint16(endView, 6, 0);
    writeUint16(endView, 8, normalized.length);
    writeUint16(endView, 10, normalized.length);
    writeUint32(endView, 12, centralDirectory.length);
    writeUint32(endView, 16, localOffset);
    writeUint16(endView, 20, 0);
    return concatBytes([...localParts, centralDirectory, end]);
  }

  function compactNumber(value) {
    const number = finiteNumber(value);
    if (number === null) {
      return String(value);
    }
    const units = [
      { threshold: 1e9, divisor: 1e9, suffix: "b" },
      { threshold: 1e6, divisor: 1e6, suffix: "m" },
      { threshold: 1e3, divisor: 1e3, suffix: "k" },
      { threshold: 0, divisor: 1, suffix: "" },
    ];
    const absolute = Math.abs(number);
    let unitIndex = units.findIndex((unit) => absolute >= unit.threshold);
    unitIndex = unitIndex < 0 ? units.length - 1 : unitIndex;
    let unit = units[unitIndex];
    let scaled = absolute / unit.divisor;
    let decimals = scaled >= 100 ? 1 : 2;
    let rounded = Number(scaled.toFixed(decimals));
    if (rounded >= 1000 && unitIndex > 0) {
      unitIndex -= 1;
      unit = units[unitIndex];
      scaled = absolute / unit.divisor;
      decimals = scaled >= 100 ? 1 : 2;
      rounded = Number(scaled.toFixed(decimals));
    }
    return `${number < 0 ? "−" : ""}${rounded}${unit.suffix}`;
  }

  function currencySymbol(currency) {
    try {
      const part = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency || "USD",
        currencyDisplay: "narrowSymbol",
      }).formatToParts(0).find((candidate) => candidate.type === "currency");
      return part ? part.value : "$";
    } catch (error) {
      return "$";
    }
  }

  function exactNumericText(parts, decimalShift) {
    if (!parts || !parts.coefficient || parts.unsafe && !Number.isSafeInteger(parts.exponent)) {
      return parts ? parts.source : "";
    }
    const exponent = parts.exponent + Number(decimalShift || 0);
    const expandedLength = parts.coefficient.length + Math.abs(exponent);
    if (!Number.isSafeInteger(exponent) || expandedLength > 10000) {
      return parts.source;
    }
    const decimalPosition = parts.coefficient.length + exponent;
    let integer;
    let fraction;
    if (decimalPosition <= 0) {
      integer = "0";
      fraction = `${"0".repeat(-decimalPosition)}${parts.coefficient}`;
    } else if (decimalPosition >= parts.coefficient.length) {
      integer = `${parts.coefficient}${"0".repeat(
        decimalPosition - parts.coefficient.length,
      )}`;
      fraction = "";
    } else {
      integer = parts.coefficient.slice(0, decimalPosition);
      fraction = parts.coefficient.slice(decimalPosition);
    }
    const groupedInteger = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    const sign = parts.negative && parts.coefficient !== "0" ? "−" : "";
    return `${sign}${groupedInteger}${fraction ? `.${fraction}` : ""}`;
  }

  function formatUnsafeNumericString(parts, kind, config) {
    const tokenSymbol = config.token_symbol ? ` ${config.token_symbol}` : "";
    if (kind === "token") {
      return `${exactNumericText(parts)}${tokenSymbol}`;
    }
    if (kind === "currency" || kind === "currency_compact") {
      const exact = exactNumericText(parts);
      const negative = exact.startsWith("−");
      const unsigned = negative ? exact.slice(1) : exact;
      return `${negative ? "−" : ""}${currencySymbol(config.currency)}${unsigned}`;
    }
    if (kind === "percent") {
      return `${exactNumericText(parts, 2)}%`;
    }
    if (kind === "percentage_points") {
      return `${exactNumericText(parts, 2)} pp`;
    }
    return exactNumericText(parts);
  }

  function formatValue(value, format, options) {
    if (isNil(value)) {
      return EMPTY_VALUE;
    }
    const config = options || {};
    const kind = String(format || "");
    const numericStringParts = unsafeNumericStringParts(value);
    const roundedCounterNumber = (
      config.compact_counter
      && numericStringParts
      && numericStringParts.unsafe
    ) ? Number(value) : null;
    const roundedCounterDisplay = Number.isFinite(roundedCounterNumber);
    const number = roundedCounterDisplay
      ? roundedCounterNumber
      : finiteNumber(value);
    if (kind === "boolean") {
      return value === true || value === 1 || value === "true" ? "Yes" : "No";
    }
    if (kind === "datetime") {
      const date = parseDate(value);
      if (!date) {
        return String(value);
      }
      return new Intl.DateTimeFormat("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
        timeZoneName: "short",
      }).format(date);
    }
    if (numericStringParts && numericStringParts.unsafe && !roundedCounterDisplay) {
      return formatUnsafeNumericString(numericStringParts, kind, config);
    }
    if (number === null) {
      return String(value);
    }
    if (kind === "currency_compact") {
      const compact = compactNumber(Math.abs(number));
      return `${number < 0 ? "−" : ""}${currencySymbol(config.currency)}${compact}`;
    }
    if (kind === "currency") {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: config.currency || "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(number);
    }
    if (kind === "percent") {
      return new Intl.NumberFormat("en-US", {
        style: "percent",
        minimumFractionDigits: 0,
        maximumFractionDigits: config.compact_counter ? 1 : 2,
      }).format(number);
    }
    if (kind === "percentage_points") {
      return `${new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 2,
      }).format(number * 100)} pp`;
    }
    if (kind === "token") {
      const decimals = Number.isInteger(config.token_decimals)
        ? Math.max(0, Math.min(12, config.token_decimals))
        : 4;
      const formatted = new Intl.NumberFormat("en-US", {
        maximumFractionDigits: decimals,
      }).format(number);
      return config.token_symbol ? `${formatted} ${config.token_symbol}` : formatted;
    }
    if (kind === "integer") {
      return new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 0,
      }).format(number);
    }
    if (kind === "integer_compact") {
      return compactNumber(number);
    }
    return new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 4,
    }).format(number);
  }

  function formatCompactDisplayValue(value, format, options) {
    const kind = String(format || "");
    const parts = unsafeNumericStringParts(value);
    if (
      parts
      && parts.unsafe
      && [
        "currency_compact",
        "integer_compact",
        "percent",
        "percentage_points",
      ].includes(kind)
    ) {
      const displayNumber = Number(value);
      if (Number.isFinite(displayNumber)) {
        return formatValue(displayNumber, kind, options);
      }
    }
    return formatValue(value, kind, options);
  }

  function formatComparison(value, format) {
    const number = finiteNumber(value);
    if (number === null) {
      return EMPTY_VALUE;
    }
    const absolute = formatValue(Math.abs(number), format || "percent");
    return `${number > 0 ? "+" : number < 0 ? "−" : ""}${absolute}`;
  }

  function formatAxisValue(value, metric) {
    const kind = metric && metric.format;
    if (kind === "currency_compact" || kind === "integer_compact") {
      return formatValue(value, kind, metric);
    }
    if (kind === "percent") {
      return formatValue(value, "percent", metric);
    }
    if (kind === "integer") {
      const number = finiteNumber(value);
      if (number !== null && Math.abs(number) >= 1000) {
        return compactNumber(number);
      }
      return formatValue(value, "integer", metric);
    }
    if (kind === "token") {
      return new Intl.NumberFormat("en-US", {
        notation: Math.abs(Number(value)) >= 10000 ? "compact" : "standard",
        maximumFractionDigits: 1,
      }).format(Number(value));
    }
    if (kind === "currency") {
      return formatValue(value, "currency_compact", metric);
    }
    const number = finiteNumber(value);
    if (number === null) {
      return String(value);
    }
    return compactNumber(number);
  }

  function formatTooltipValue(value, format, options) {
    const config = options || {};
    const kind = String(format || config.format || "");
    const parsed = finiteNumber(value);
    const displayNumber = parsed === null && typeof value === "string"
      ? Number(value)
      : parsed;
    const safeValue = Number.isFinite(displayNumber) ? displayNumber : value;
    let formatted;
    if (kind === "currency" || kind === "currency_compact") {
      formatted = formatValue(safeValue, "currency_compact", config);
    } else if (kind === "integer" || kind === "integer_compact") {
      formatted = Math.abs(Number(safeValue)) >= 1000
        ? formatValue(safeValue, "integer_compact", config)
        : formatValue(safeValue, "integer", config);
    } else if (kind === "percent" || kind === "percentage_points") {
      formatted = formatValue(safeValue, kind, config);
    } else {
      formatted = formatAxisValue(safeValue, { ...config, format: kind });
    }
    return Boolean(config.tooltip_signed || config.signed)
      && Number(safeValue) > 0
      ? `+${formatted}`
      : formatted;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function shortAddress(value) {
    const text = String(value || "");
    if (text.length <= 11) {
      return text;
    }
    return `${text.slice(0, 5)}…${text.slice(-5)}`;
  }

  function normalizeChain(value) {
    const chain = String(value || "").trim().toLocaleLowerCase("en");
    if (["ethereum", "eth", "mainnet", "ethereum mainnet"].includes(chain)) {
      return "ethereum";
    }
    if (["arbitrum one", "arb", "arbitrum_one"].includes(chain)) {
      return "arbitrum";
    }
    if (["base mainnet", "base_mainnet"].includes(chain)) {
      return "base";
    }
    if (["optimism mainnet", "op", "optimism_mainnet"].includes(chain)) {
      return "optimism";
    }
    if (["matic", "polygon pos", "polygon_pos"].includes(chain)) {
      return "polygon";
    }
    if (["bsc", "binance smart chain", "bnb chain"].includes(chain)) {
      return "bnb";
    }
    return chain;
  }

  function explorerDetails(chain) {
    return EVM_EXPLORERS[normalizeChain(chain)] || null;
  }

  function explorerUrl(value, kind, chain) {
    const identifier = String(value || "").trim();
    const normalizedKind = kind === "transaction" || kind === "tx"
      ? "tx"
      : kind === "address"
        ? "address"
        : "";
    const explorer = explorerDetails(chain);
    if (!explorer || !normalizedKind || !/^0x[0-9a-f]+$/i.test(identifier)) {
      return "";
    }
    const expectedLength = normalizedKind === "address" ? 42 : 66;
    if (identifier.length !== expectedLength) {
      return "";
    }
    return `${explorer.baseUrl}/${normalizedKind}/${identifier}`;
  }

  function shortDate(value) {
    const date = parseDate(value);
    if (!date) {
      return String(value || "");
    }
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      timeZone: "UTC",
    }).format(date);
  }

  function longDate(value) {
    const date = parseDate(value);
    if (!date) {
      return "";
    }
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  function utcTimestampLabel(value) {
    const date = parseDate(value);
    if (!date) {
      return String(value || "");
    }
    const dateLabel = new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
    const timeLabel = new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC",
    }).format(date);
    return `${dateLabel} · ${timeLabel} UTC`;
  }

  function utcTimestampDetailLabel(value) {
    const date = parseUtcTimestamp(value);
    if (!date) {
      return String(value || "");
    }
    const dateLabel = new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
    const timeLabel = new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZone: "UTC",
    }).format(date);
    return `${dateLabel} · ${timeLabel} UTC`;
  }

  function updateRelativeAgeElement(element, referenceTime) {
    if (!element || !element.dataset) {
      return;
    }
    const sourceTimestamp = element.dataset.relativeTimestamp;
    const parsed = parseUtcTimestamp(sourceTimestamp);
    if (!parsed) {
      return;
    }
    const age = relativeAgeLabel(parsed, referenceTime);
    const fullTimestamp = utcTimestampDetailLabel(parsed);
    element.textContent = age;
    element.dateTime = parsed.toISOString();
    element.setAttribute("datetime", parsed.toISOString());
    element.title = fullTimestamp;
    element.dataset.fullTimestamp = fullTimestamp;
    element.setAttribute("aria-label", `${age}. ${fullTimestamp}`);
  }

  function refreshRelativeAgeLabels(scope, referenceTime) {
    if (!scope || typeof scope.querySelectorAll !== "function") {
      return;
    }
    scope.querySelectorAll("[data-relative-timestamp]").forEach((element) => {
      updateRelativeAgeElement(element, referenceTime);
    });
  }

  function startRelativeAgeRefresh(state) {
    if (
      !state
      || state.relativeAgeTimer !== null
      || !root
      || typeof root.setInterval !== "function"
    ) {
      return;
    }
    refreshRelativeAgeLabels(state.page);
    state.relativeAgeTimer = root.setInterval(() => {
      if (state.page && state.page.isConnected === false) {
        root.clearInterval(state.relativeAgeTimer);
        state.relativeAgeTimer = null;
        return;
      }
      refreshRelativeAgeLabels(state.page);
    }, RELATIVE_AGE_REFRESH_MS);
    if (
      state.relativeAgeTimer
      && typeof state.relativeAgeTimer.unref === "function"
    ) {
      state.relativeAgeTimer.unref();
    }
  }

  function dateStamp(value) {
    const date = parseDate(value);
    return date ? date.toISOString().slice(0, 10) : "";
  }

  function safeFilename(value) {
    return String(value || "studio-export")
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 120) || "studio-export";
  }

  function createElement(scope, tag, className, text) {
    const element = scope.createElement(tag);
    if (className) {
      element.className = className;
    }
    if (text !== undefined) {
      element.textContent = String(text);
    }
    return element;
  }

  function clearMetricBody(state, metricId) {
    const chart = state.charts.get(metricId);
    if (chart) {
      try {
        chart.dispose();
      } catch (error) {
        // A detached chart can already be disposed by ECharts.
      }
      state.charts.delete(metricId);
    }
    const body = state.page.querySelector(`[data-metric-render="${metricId}"]`);
    if (body) {
      body.replaceChildren();
      body.removeAttribute("aria-busy");
    }
    return body;
  }

  function renderMetricState(state, metric, kind, title, message) {
    const body = clearMetricBody(state, metric.id);
    if (!body) {
      return;
    }
    body.dataset.state = kind;
    const card = createElement(
      body.ownerDocument,
      "div",
      `studio-metric-state studio-${kind}-state`,
    );
    card.appendChild(createElement(body.ownerDocument, "strong", "", title));
    if (message) {
      card.appendChild(createElement(body.ownerDocument, "p", "", message));
    }
    body.appendChild(card);
  }

  function uniqueColumns(values) {
    const seen = new Set();
    return (Array.isArray(values) ? values : []).filter((value) => {
      const column = typeof value === "string" ? value.trim() : "";
      if (!column || seen.has(column)) {
        return false;
      }
      seen.add(column);
      return true;
    });
  }

  function validateExpectedColumns(rows, expectedColumns, declaredColumns) {
    const expected = uniqueColumns(expectedColumns);
    const declared = Array.isArray(declaredColumns)
      ? new Set(uniqueColumns(declaredColumns))
      : null;
    const missingColumns = declared
      ? expected.filter((column) => !declared.has(column))
      : [];
    const rowErrors = [];
    if (Array.isArray(rows)) {
      rows.forEach((row, rowIndex) => {
        const missing = row && typeof row === "object" && !Array.isArray(row)
          ? expected.filter((column) => !Object.prototype.hasOwnProperty.call(row, column))
          : expected.slice();
        if (missing.length || !row || typeof row !== "object" || Array.isArray(row)) {
          rowErrors.push({
            rowIndex,
            missingColumns: missing,
            invalidRow: !row || typeof row !== "object" || Array.isArray(row),
          });
          missing.forEach((column) => {
            if (!missingColumns.includes(column)) {
              missingColumns.push(column);
            }
          });
        }
      });
    }
    return {
      valid: missingColumns.length === 0 && rowErrors.length === 0,
      expectedColumns: expected,
      missingColumns,
      rowErrors,
    };
  }

  function sourceFailure(code, title, hint, metadata) {
    return {
      data: {
        error: title,
        hint,
        code,
      },
      meta: {
        ...(metadata || {}),
        status: code,
        result_status: "failed",
        snapshot_state: "unavailable",
        stale: false,
        delayed: false,
      },
    };
  }

  function normalizedSourceMetadata(descriptor, payloadMeta) {
    const source = payloadMeta || {};
    const generatedAt = source.generated_at
      || source.last_refreshed
      || (descriptor && descriptor.generatedAt)
      || "";
    return {
      query_id: descriptor && descriptor.queryId !== undefined
        ? descriptor.queryId
        : source.query_id,
      query_url: (descriptor && descriptor.queryUrl) || source.query_url || "",
      data_file: (descriptor && descriptor.dataFile) || source.data_file || "",
      generated_at: generatedAt,
      execution_id: source.execution_id
        || (descriptor && descriptor.executionId)
        || "",
      execution_finished_at: source.execution_finished_at
        || (descriptor && descriptor.executionFinishedAt)
        || generatedAt,
      data_updated_at: source.data_updated_at
        || (descriptor && descriptor.dataUpdatedAt)
        || source.execution_finished_at
        || generatedAt,
      display_updated_at: source.display_updated_at
        || (descriptor && descriptor.displayUpdatedAt)
        || "",
      freshness_status: source.freshness_status
        || (descriptor && descriptor.freshnessStatus)
        || "",
      freshness_policy: source.freshness_policy
        || (descriptor && descriptor.freshnessPolicy)
        || null,
      row_count: source.row_count !== undefined
        ? source.row_count
        : descriptor && descriptor.rowCount,
      columns: Array.isArray(source.columns)
        ? source.columns.slice()
        : uniqueColumns(descriptor && descriptor.expectedColumns),
      result_status: source.result_status || source.status || "",
      snapshot_id: source.snapshot_id
        || (descriptor && descriptor.snapshotId)
        || "",
      snapshot_state: source.snapshot_state || "current",
    };
  }

  function isSourceStale(metadata, staleAfterHours, nowValue) {
    const threshold = Number(staleAfterHours);
    if (!Number.isFinite(threshold) || threshold <= 0) {
      return false;
    }
    const sourceTime = parseDate(
      metadata
      && (metadata.execution_finished_at || metadata.generated_at),
    );
    const now = parseDate(nowValue === undefined ? new Date() : nowValue);
    if (!sourceTime || !now || now <= sourceTime) {
      return false;
    }
    return now.getTime() - sourceTime.getTime() > threshold * 60 * 60 * 1000;
  }

  function freshnessPriority(value) {
    return ({ current: 0, delayed: 1, stale: 2 })[
      String(value || "").toLocaleLowerCase("en")
    ];
  }

  function classifySourceFreshness(metadata, policy, nowValue) {
    const source = metadata || {};
    const settings = policy && typeof policy === "object" ? policy : {};
    const explicit = String(source.freshness_status || "")
      .toLocaleLowerCase("en");
    let computed = "current";
    const sourceTime = parseDate(
      source.execution_finished_at
      || source.data_updated_at
      || source.generated_at,
    );
    const now = parseDate(nowValue === undefined ? new Date() : nowValue);
    const delayedAfter = finiteNumber(
      settings.warning_after_hours
      ?? settings.warningAfterHours
      ?? settings.expected_refresh_hours
      ?? settings.expectedRefreshHours,
    );
    const staleAfter = finiteNumber(
      settings.stale_after_hours
      ?? settings.staleAfterHours,
    );
    if (sourceTime && now && now > sourceTime) {
      const ageHours = (now.getTime() - sourceTime.getTime()) / (60 * 60 * 1000);
      if (staleAfter !== null && staleAfter > 0 && ageHours > staleAfter) {
        computed = "stale";
      } else if (
        delayedAfter !== null
        && delayedAfter > 0
        && ageHours > delayedAfter
      ) {
        computed = "delayed";
      }
    }
    const explicitPriority = freshnessPriority(explicit);
    return explicitPriority !== undefined
      && explicitPriority > freshnessPriority(computed)
      ? explicit
      : computed;
  }

  function missingColumnsFailure(validation, metadata) {
    const missing = validation.missingColumns.length
      ? validation.missingColumns.join(", ")
      : "one or more configured fields";
    const firstRow = validation.rowErrors.length
      ? ` The first invalid row is ${validation.rowErrors[0].rowIndex + 1}.`
      : "";
    return sourceFailure(
      "missing_columns",
      "An expected column is missing.",
      `The generated result does not provide: ${missing}.${firstRow}`,
      metadata,
    );
  }

  function normalizeDemoBundle(payload, descriptor, sourceName, nowValue) {
    const config = descriptor || {};
    const metadata = normalizedSourceMetadata(config, payload && payload.meta);
    if (
      !payload
      || typeof payload !== "object"
      || Array.isArray(payload)
      || !payload.datasets
      || typeof payload.datasets !== "object"
      || Array.isArray(payload.datasets)
    ) {
      return sourceFailure(
        "malformed",
        "The demo data file is malformed.",
        "The file must contain a datasets mapping.",
        metadata,
      );
    }
    const datasetName = config.dataset || sourceName;
    if (!Object.prototype.hasOwnProperty.call(payload.datasets, datasetName)) {
      return sourceFailure(
        "unavailable",
        "The configured data source is unavailable.",
        `The demo bundle does not contain “${datasetName}”.`,
        metadata,
      );
    }
    const rows = payload.datasets[datasetName];
    if (rows && !Array.isArray(rows) && typeof rows === "object" && rows.error) {
      return sourceFailure(
        "failed",
        String(rows.error),
        rows.hint || "Review the source query before the next refresh.",
        metadata,
      );
    }
    if (!Array.isArray(rows)) {
      return sourceFailure(
        "malformed",
        "The configured data source is malformed.",
        "Studio expected a list of result rows.",
        metadata,
      );
    }
    const inferred = rows.length ? inferredColumns(rows) : null;
    const validation = validateExpectedColumns(
      rows,
      config.expectedColumns,
      inferred,
    );
    if (!validation.valid) {
      return missingColumnsFailure(validation, metadata);
    }
    const columns = inferred || uniqueColumns(config.expectedColumns);
    const freshnessStatus = classifySourceFreshness(
      metadata,
      config.freshnessPolicy
        || metadata.freshness_policy
        || { staleAfterHours: config.staleAfterHours },
      nowValue,
    );
    return {
      data: rows.slice(),
      meta: {
        ...metadata,
        status: rows.length ? "success" : "empty",
        result_status: rows.length ? "success" : "empty",
        freshness_status: freshnessStatus,
        snapshot_state: "current",
        stale: freshnessStatus === "stale",
        delayed: freshnessStatus === "delayed",
        row_count: rows.length,
        columns,
      },
      dashboardMeta: { ...(payload.meta || {}) },
    };
  }

  function normalizeManifest(payload) {
    const queries = payload && Array.isArray(payload.queries)
      ? payload.queries
      : null;
    const generatedAt = payload && (payload.generated_at || payload.last_refreshed);
    const bootstrap = queries
      && queries.length === 0
      && (payload.generated_at === null || payload.generated_at === undefined)
      && !payload.last_refreshed;
    if (
      !payload
      || typeof payload !== "object"
      || Array.isArray(payload)
      || Number(payload.schema_version) !== 1
      || !queries
      || (!bootstrap && !parseDate(generatedAt))
    ) {
      throw new Error("The Studio generated-data manifest is malformed.");
    }
    if (!bootstrap && (
      queries.length === 0
      ||
      typeof payload.snapshot_id !== "string"
      || !/^[a-z0-9][a-z0-9._-]{0,127}$/.test(payload.snapshot_id)
      || !["fixture", "live", "mixed"].includes(payload.mode)
      || payload.validation_status !== "valid"
      || (
        payload.dashboard_refreshed_at !== undefined
        && !parseDate(payload.dashboard_refreshed_at)
      )
      || !parseDate(payload.display_updated_at)
      || !parseDate(payload.data_updated_at)
    )) {
      throw new Error("The Studio active-snapshot manifest is incomplete.");
    }
    const seenQueryIds = new Set();
    const seenDataFiles = new Set();
    const normalizedQueries = queries.map((query, index) => {
      const required = [
        "query_id",
        "query_url",
        "generated_at",
        "execution_id",
        "execution_finished_at",
        "status",
        "freshness_status",
        "row_count",
        "columns",
        "data_file",
      ];
      if (
        !query
        || typeof query !== "object"
        || Array.isArray(query)
        || !Number.isInteger(Number(query.query_id))
        || Number(query.query_id) <= 0
        || typeof query.query_url !== "string"
        || !query.query_url.trim()
        || typeof query.data_file !== "string"
        || !query.data_file.trim()
        || required.some((field) => query[field] === undefined || query[field] === "")
        || !Array.isArray(query.columns)
        || query.columns.some((column) => typeof column !== "string" || !column.trim())
        || !parseDate(query.generated_at)
        || typeof query.execution_id !== "string"
        || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(query.execution_id)
        || !parseDate(query.execution_finished_at)
        || (
          query.data_updated_at !== undefined
          && !parseDate(query.data_updated_at)
        )
        || !Number.isInteger(query.row_count)
        || query.row_count < 0
        || !["success", "empty", "failed"].includes(query.status)
        || !["current", "delayed", "stale"].includes(query.freshness_status)
      ) {
        throw new Error(`Manifest query entry ${index + 1} is malformed.`);
      }
      try {
        manifestResultUrl("manifest.json", query);
      } catch (error) {
        throw new Error(`Manifest query entry ${index + 1} has an unsafe data file.`);
      }
      const queryId = Number(query.query_id);
      const dataFile = String(query.data_file);
      if (dataFile !== `query_${queryId}.json`) {
        throw new Error(`Manifest query entry ${index + 1} has the wrong data file.`);
      }
      if (seenQueryIds.has(queryId) || seenDataFiles.has(dataFile)) {
        throw new Error("The Studio generated-data manifest has duplicate query entries.");
      }
      seenQueryIds.add(queryId);
      seenDataFiles.add(dataFile);
      return {
        ...query,
        query_id: queryId,
        columns: Array.isArray(query.columns) ? query.columns.slice() : [],
      };
    });
    const artifacts = payload.artifacts === undefined
      ? []
      : payload.artifacts;
    if (!Array.isArray(artifacts)) {
      throw new Error("The Studio generated-data artifact manifest is malformed.");
    }
    const seenArtifactIds = new Set();
    const normalizedArtifacts = artifacts.map((artifact, index) => {
      const artifactId = String(
        artifact && (artifact.artifact_id || artifact.id || artifact.data_source) || "",
      ).trim();
      const dataFile = String(artifact && artifact.data_file || "").trim();
      if (
        !artifact
        || typeof artifact !== "object"
        || Array.isArray(artifact)
        || !/^[a-z0-9][a-z0-9._-]{0,127}$/.test(artifactId)
        || !/^[a-z0-9][a-z0-9._-]{0,127}\.json$/.test(dataFile)
        || seenArtifactIds.has(artifactId)
      ) {
        throw new Error(`Manifest artifact entry ${index + 1} is malformed.`);
      }
      seenArtifactIds.add(artifactId);
      return {
        ...artifact,
        id: artifactId,
        artifact_id: artifactId,
        data_source: String(artifact.data_source || artifactId),
        data_file: dataFile,
      };
    });
    return {
      ...payload,
      generated_at: payload.generated_at || payload.last_refreshed || "",
      queries: normalizedQueries,
      ...(payload.artifacts === undefined ? {} : { artifacts: normalizedArtifacts }),
    };
  }

  function normalizeRefreshStatus(payload) {
    const latestAttemptStatus = payload && payload.latest_attempt_status;
    if (
      !payload
      || typeof payload !== "object"
      || Array.isArray(payload)
      || Number(payload.schema_version) !== 2
      || typeof payload.current_snapshot_id !== "string"
      || !/^[a-z0-9][a-z0-9._-]{0,127}$/.test(payload.current_snapshot_id)
      || (
        payload.previous_snapshot_id !== null
        && payload.previous_snapshot_id !== undefined
        && (
          typeof payload.previous_snapshot_id !== "string"
          || !/^[a-z0-9][a-z0-9._-]{0,127}$/.test(payload.previous_snapshot_id)
        )
      )
      || !["success", "unchanged", "failed", "partial"].includes(latestAttemptStatus)
      || typeof payload.using_previous !== "boolean"
      || (
        payload.using_previous
        && !["failed", "partial"].includes(latestAttemptStatus)
      )
      || !parseDate(payload.last_checked_at)
      || !Object.prototype.hasOwnProperty.call(payload, "latest_failure")
      || (
        payload.latest_failure !== null
        && payload.latest_failure !== undefined
        && (
          typeof payload.latest_failure !== "object"
          || Array.isArray(payload.latest_failure)
        )
      )
      || (
        ["failed", "partial"].includes(latestAttemptStatus)
        && (
          !payload.latest_failure
          || typeof payload.latest_failure !== "object"
          || Array.isArray(payload.latest_failure)
        )
      )
    ) {
      throw new Error("The Studio refresh status is malformed.");
    }
    return {
      ...payload,
      latest_attempt_status: latestAttemptStatus,
      using_previous: payload.using_previous,
    };
  }

  function siblingDataUrl(referenceUrl, fileName) {
    const reference = String(referenceUrl || "");
    const suffixIndex = reference.search(/[?#]/);
    const cleanReference = suffixIndex === -1
      ? reference
      : reference.slice(0, suffixIndex);
    const slashIndex = cleanReference.lastIndexOf("/");
    return `${slashIndex === -1 ? "" : cleanReference.slice(0, slashIndex + 1)}`
      + fileName;
  }

  function manifestResultUrl(manifestUrl, manifestEntry) {
    const fileName = manifestEntry && manifestEntry.data_file;
    if (
      typeof fileName !== "string"
      || !/^query_[1-9][0-9]*\.json$/.test(fileName)
    ) {
      const error = new Error("The manifest query file path is unsafe.");
      error.code = "malformed";
      throw error;
    }
    return siblingDataUrl(manifestUrl, fileName);
  }

  function manifestArtifactUrl(manifestUrl, manifestEntry) {
    const fileName = manifestEntry && manifestEntry.data_file;
    if (
      typeof fileName !== "string"
      || !/^[a-z0-9][a-z0-9._-]{0,127}\.json$/.test(fileName)
    ) {
      const error = new Error("The manifest artifact file path is unsafe.");
      error.code = "malformed";
      throw error;
    }
    return siblingDataUrl(manifestUrl, fileName);
  }

  function manifestAgreementErrors(payload, descriptor, manifestEntry) {
    if (!manifestEntry) {
      return [];
    }
    const config = descriptor || {};
    const errors = [];
    const scalarFields = [
      "query_id",
      "query_url",
      "generated_at",
      "execution_id",
      "execution_finished_at",
      "data_updated_at",
      "status",
      "freshness_status",
      "row_count",
      "checksum",
      "validation_status",
      "mode",
      "source_query_id",
      "source_execution_id",
      "source_last_updated",
      "methodology_id",
      "methodology_version",
      "script_path",
      "script_checksum",
      "raw_checksum",
    ];
    scalarFields.forEach((field) => {
      const fileValue = payload[field];
      const manifestValue = manifestEntry[field];
      if (
        fileValue !== undefined
        && manifestValue !== undefined
        && String(fileValue) !== String(manifestValue)
      ) {
        errors.push(field);
      }
    });
    if (
      Array.isArray(payload.columns)
      && Array.isArray(manifestEntry.columns)
      && (
        payload.columns.length !== manifestEntry.columns.length
        || payload.columns.some((column, index) => column !== manifestEntry.columns[index])
      )
    ) {
      errors.push("columns");
    }
    if (
      payload.freshness_policy !== undefined
      && manifestEntry.freshness_policy !== undefined
      && JSON.stringify(payload.freshness_policy)
        !== JSON.stringify(manifestEntry.freshness_policy)
    ) {
      errors.push("freshness_policy");
    }
    if (
      config.dataFile
      && manifestEntry.data_file
      && String(config.dataFile) !== String(manifestEntry.data_file)
    ) {
      errors.push("data_file");
    }
    return errors;
  }

  function normalizeGeneratedQuery(
    payload,
    descriptor,
    nowValue,
    manifestEntry,
  ) {
    const config = descriptor || {};
    const metadata = normalizedSourceMetadata(config, {
      ...(manifestEntry || {}),
      ...(payload && typeof payload === "object" ? payload : {}),
    });
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return sourceFailure(
        "malformed",
        "The generated query file is malformed.",
        "Studio expected a self-describing query result object.",
        metadata,
      );
    }
    const requiredMetadata = [
      "schema_version",
      "query_id",
      "query_url",
      "generated_at",
      "execution_id",
      "execution_finished_at",
      "status",
      "freshness_status",
      "row_count",
      "columns",
    ];
    if (
      Number(payload.schema_version) !== 1
      || requiredMetadata.some(
        (field) => payload[field] === undefined || payload[field] === "",
      )
      || !parseDate(payload.generated_at)
      || typeof payload.execution_id !== "string"
      || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(payload.execution_id)
      || !parseDate(payload.execution_finished_at)
    ) {
      return sourceFailure(
        "malformed",
        "The generated query metadata is incomplete.",
        "The file does not satisfy Studio generated-query schema version 1.",
        metadata,
      );
    }
    if (
      config.queryId !== undefined
      && Number(payload.query_id) !== Number(config.queryId)
    ) {
      return sourceFailure(
        "malformed",
        "The generated query file has the wrong query ID.",
        `Expected query ${config.queryId}, received ${payload.query_id}.`,
        metadata,
      );
    }
    if (
      config.queryUrl
      && String(payload.query_url).replace(/\/+$/, "")
        !== String(config.queryUrl).replace(/\/+$/, "")
    ) {
      return sourceFailure(
        "malformed",
        "The generated query file has the wrong query URL.",
        `Expected ${config.queryUrl}, received ${payload.query_url}.`,
        metadata,
      );
    }
    const agreementErrors = manifestAgreementErrors(
      payload,
      config,
      manifestEntry,
    );
    if (agreementErrors.length) {
      return sourceFailure(
        "malformed",
        "The generated query file does not match its manifest.",
        `Mismatched fields: ${agreementErrors.join(", ")}.`,
        metadata,
      );
    }
    const status = String(payload.status || "").toLocaleLowerCase("en");
    if (!["current", "delayed", "stale"].includes(payload.freshness_status)) {
      return sourceFailure(
        "malformed",
        "The generated query freshness status is invalid.",
        "Expected current, delayed, or stale freshness metadata.",
        metadata,
      );
    }
    if (status === "failed") {
      return sourceFailure(
        "failed",
        payload.error || "The source query failed.",
        "The last successful snapshot was not replaced.",
        metadata,
      );
    }
    if (!["success", "empty"].includes(status)) {
      return sourceFailure(
        "malformed",
        "The generated query status is invalid.",
        "Expected a successful, empty, or failed query status.",
        metadata,
      );
    }
    if (!Array.isArray(payload.columns) || !Array.isArray(payload.rows)) {
      return sourceFailure(
        "malformed",
        "The generated query file is malformed.",
        "Successful query files must contain columns and rows lists.",
        metadata,
      );
    }
    if (
      !Number.isInteger(payload.row_count)
      || payload.row_count < 0
      || payload.row_count !== payload.rows.length
      || (status === "success" && payload.row_count === 0)
      || (status === "empty" && payload.row_count !== 0)
    ) {
      return sourceFailure(
        "malformed",
        "The generated query row count is invalid.",
        "row_count must exactly match the number of result rows.",
        metadata,
      );
    }
    const validation = validateExpectedColumns(
      payload.rows,
      config.expectedColumns,
      payload.columns,
    );
    if (!validation.valid) {
      return missingColumnsFailure(validation, metadata);
    }
    const freshnessStatus = classifySourceFreshness(
      metadata,
      config.freshnessPolicy
        || metadata.freshness_policy
        || { staleAfterHours: config.staleAfterHours },
      nowValue,
    );
    return {
      data: payload.rows.slice(),
      meta: {
        ...metadata,
        status: payload.rows.length ? "success" : "empty",
        result_status: payload.rows.length ? "success" : "empty",
        freshness_status: freshnessStatus,
        snapshot_state: "current",
        stale: freshnessStatus === "stale",
        delayed: freshnessStatus === "delayed",
        row_count: payload.rows.length,
        columns: payload.columns.slice(),
      },
    };
  }

  function derivedArtifactId(descriptor, sourceName) {
    return String(
      descriptor && (
        descriptor.artifactId
        || descriptor.artifact_id
        || descriptor.dataSource
        || descriptor.data_source
      )
      || sourceName
      || "",
    ).trim();
  }

  function normalizeGeneratedDerived(
    payload,
    descriptor,
    sourceName,
    nowValue,
    manifestEntry,
  ) {
    const config = descriptor || {};
    const artifactId = derivedArtifactId(config, sourceName);
    const metadata = normalizedSourceMetadata(config, {
      ...(manifestEntry || {}),
      ...(payload && typeof payload === "object" ? payload : {}),
    });
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return sourceFailure(
        "malformed",
        "The generated derived data file is malformed.",
        "Studio expected a self-describing derived artifact.",
        metadata,
      );
    }
    const payloadArtifactId = String(
      payload.artifact_id || payload.id || payload.data_source || "",
    ).trim();
    const wallets = Array.isArray(payload.wallets)
      ? payload.wallets
      : Array.isArray(payload.rows) ? payload.rows : null;
    const walletIndex = payload.wallet_index;
    const rowCount = Number(payload.row_count);
    if (
      Number(payload.schema_version) !== 1
      || !payloadArtifactId
      || artifactId && payloadArtifactId !== artifactId
      || !parseDate(payload.generated_at)
      || !wallets
      || !walletIndex
      || typeof walletIndex !== "object"
      || Array.isArray(walletIndex)
      || !payload.concentration
      || typeof payload.concentration !== "object"
      || Array.isArray(payload.concentration)
      || !Number.isInteger(rowCount)
      || rowCount !== wallets.length
    ) {
      return sourceFailure(
        "malformed",
        "The generated derived data contract is incomplete.",
        "The wallet summary, wallet index, and concentration data must reconcile.",
        metadata,
      );
    }
    const invalidWallet = wallets.some((wallet) => (
      !wallet
      || typeof wallet !== "object"
      || Array.isArray(wallet)
      || !/^0x[0-9a-f]{40}$/i.test(String(wallet.address || ""))
    ));
    const invalidIndex = Object.entries(walletIndex).some(([address, offset]) => (
      address !== address.toLocaleLowerCase("en")
      || !/^0x[0-9a-f]{40}$/.test(address)
      || !Number.isInteger(Number(offset))
      || Number(offset) < 0
      || Number(offset) >= wallets.length
      || String(wallets[Number(offset)].address || "").toLocaleLowerCase("en") !== address
    ));
    if (invalidWallet || invalidIndex) {
      return sourceFailure(
        "malformed",
        "The generated wallet index is invalid.",
        "Every lowercase wallet key must resolve to the matching wallet summary.",
        metadata,
      );
    }
    const freshnessStatus = classifySourceFreshness(
      metadata,
      config.freshnessPolicy || metadata.freshness_policy,
      nowValue,
    );
    return {
      data: {
        ...payload,
        artifact_id: payloadArtifactId,
        data_source: String(payload.data_source || payloadArtifactId),
        wallets: wallets.slice(),
        wallet_index: { ...walletIndex },
        concentration: { ...payload.concentration },
      },
      meta: {
        ...metadata,
        artifact_id: payloadArtifactId,
        data_source: String(payload.data_source || payloadArtifactId),
        source_query_ids: Array.isArray(payload.source_query_ids)
          ? payload.source_query_ids.slice()
          : [],
        source_executions: payload.source_executions
          && typeof payload.source_executions === "object"
          ? { ...payload.source_executions }
          : {},
        status: wallets.length ? "success" : "empty",
        result_status: wallets.length ? "success" : "empty",
        freshness_status: freshnessStatus,
        snapshot_state: "current",
        stale: freshnessStatus === "stale",
        delayed: freshnessStatus === "delayed",
        row_count: wallets.length,
        columns: Array.isArray(payload.columns) ? payload.columns.slice() : [],
      },
    };
  }

  function requiredColumnsForMetric(metric) {
    const required = Array.isArray(metric && metric.columns)
      ? metric.columns.slice()
      : [];
    if (metric && metric.comparison_column) {
      required.push(metric.comparison_column);
    }
    return uniqueColumns(required);
  }

  function sourceMetadataForMetric(state, metric, sourceName) {
    const metadata = state
      && state.data
      && state.data.sourceMeta;
    const name = sourceName || metric && (
      metric.derived_data_source || metric.data_source
    );
    return metadata
      && metadata[name]
      ? metadata[name]
      : {};
  }

  function sourceForMetric(state, metric, sourceName) {
    const datasets = state.data && state.data.datasets;
    const name = sourceName || metric.derived_data_source || metric.data_source;
    if (!datasets || !Object.prototype.hasOwnProperty.call(datasets, name)) {
      return {
        error: `Generated data source “${name}” is unavailable.`,
        hint: "Refresh the Studio data snapshot and try again.",
      };
    }
    return datasets[name];
  }

  function isEvmAddress(value) {
    return /^0x[0-9a-f]{40}$/i.test(String(value || "").trim());
  }

  function normalizeWalletAddress(value) {
    const address = String(value || "").trim();
    return isEvmAddress(address) ? address.toLocaleLowerCase("en") : "";
  }

  function isUsableSource(source) {
    return Array.isArray(source) || Boolean(
      source
      && typeof source === "object"
      && !Array.isArray(source)
      && !source.error
      && (
        Array.isArray(source.wallets)
        || Array.isArray(source.rows)
        || source.wallet_index && typeof source.wallet_index === "object"
      ),
    );
  }

  function intelligenceWallets(source) {
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      return [];
    }
    const rows = Array.isArray(source.wallets)
      ? source.wallets
      : Array.isArray(source.rows) ? source.rows : [];
    return rows.filter((row) => row && typeof row === "object" && !Array.isArray(row));
  }

  function intelligenceWalletForAddress(source, address) {
    const normalized = normalizeWalletAddress(address);
    if (!normalized) {
      return null;
    }
    const wallets = intelligenceWallets(source);
    const index = source && source.wallet_index;
    const indexed = index && typeof index === "object" && !Array.isArray(index)
      ? index[normalized]
      : undefined;
    if (Number.isInteger(Number(indexed))) {
      const wallet = wallets[Number(indexed)];
      if (wallet && normalizeWalletAddress(wallet.address) === normalized) {
        return wallet;
      }
    } else if (indexed && typeof indexed === "object" && !Array.isArray(indexed)) {
      return indexed.summary && typeof indexed.summary === "object"
        ? { ...indexed.summary, ...indexed }
        : indexed;
    }
    return wallets.find((wallet) => normalizeWalletAddress(wallet.address) === normalized) || null;
  }

  function intelligenceWalletCollection(wallet, keys) {
    if (!wallet || typeof wallet !== "object") {
      return [];
    }
    for (const key of keys) {
      if (Array.isArray(wallet[key])) {
        return wallet[key];
      }
    }
    return [];
  }

  function intelligenceGlobalCollection(source, keys) {
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      return [];
    }
    for (const key of keys) {
      if (Array.isArray(source[key])) {
        return source[key].slice();
      }
    }
    return intelligenceWallets(source).flatMap((wallet) => (
      intelligenceWalletCollection(wallet, keys).map((row) => ({
        ...row,
        address: row && row.address || wallet.address,
      }))
    ));
  }

  function intelligenceRankedWallets(source) {
    return intelligenceWallets(source)
      .slice()
      .sort((left, right) => (
        compareValues(
          right && right.total_referral_deposits_usd,
          left && left.total_referral_deposits_usd,
        )
        || String(left && left.address || "")
          .localeCompare(String(right && right.address || ""), "en", { sensitivity: "base" })
      ))
      .map((wallet, index) => ({
        ...wallet,
        rank: index + 1,
      }));
  }

  function intelligenceRowsForComponent(source, component) {
    if (!isUsableSource(source)) {
      return source;
    }
    if (Array.isArray(source)) {
      return source.slice();
    }
    if ([
      "top_referred_depositors",
      "top_depositors",
      "referral_concentration",
      "wallet_investigation",
    ].includes(component)) {
      return intelligenceRankedWallets(source);
    }
    if (component === "recent_referral_deposits") {
      return intelligenceGlobalCollection(source, [
        "recent_referral_deposits",
        "referral_deposits",
        "deposits",
      ]).sort((left, right) => compareValues(
        right && (right.block_time || right.timestamp),
        left && (left.block_time || left.timestamp),
      ));
    }
    if (component === "recent_etherfi_activity") {
      return intelligenceGlobalCollection(source, [
        "recent_etherfi_activity",
        "activity",
        "activities",
      ]).sort((left, right) => compareValues(
        right && (right.block_time || right.timestamp),
        left && (left.block_time || left.timestamp),
      ));
    }
    return intelligenceWallets(source).slice();
  }

  function rawRowsForMetric(state, metric) {
    const source = sourceForMetric(state, metric);
    const resolved = metric && metric.intelligence_component
      ? intelligenceRowsForComponent(source, metric.intelligence_component)
      : source;
    if (!Array.isArray(resolved)) {
      return source;
    }
    const derivedColumns = metric && metric.derived_data_source
      ? (
        Array.isArray(metric.table_columns) ? metric.table_columns
          : Array.isArray(metric.intelligence_columns) ? metric.intelligence_columns
            : []
      )
      : requiredColumnsForMetric(metric);
    const validation = validateExpectedColumns(
      resolved,
      derivedColumns,
      metric && metric.derived_data_source && metric.intelligence_component
        ? uniqueColumns([
          ...(sourceMetadataForMetric(state, metric).columns || []),
          ...inferredColumns(resolved),
        ])
        : sourceMetadataForMetric(state, metric).columns,
    );
    if (!validation.valid) {
      return missingColumnsFailure(
        validation,
        sourceMetadataForMetric(state, metric),
      ).data;
    }
    return resolved.slice();
  }

  function periodKeyForMetric(metric, range) {
    const mapping = metric && metric.period_key_map;
    if (!mapping || typeof mapping !== "object" || Array.isArray(mapping)) {
      return "";
    }
    const requestedRange = String(range || "");
    const configured = Object.prototype.hasOwnProperty.call(mapping, requestedRange)
      ? mapping[requestedRange]
      : mapping[requestedRange.toLocaleLowerCase("en")];
    return isNil(configured) ? "" : String(configured);
  }

  function selectPeriodRow(rows, metric, range) {
    const values = Array.isArray(rows) ? rows : [];
    const periodColumn = metric && metric.period_key_column;
    if (!periodColumn) {
      return values.length ? values[0] : null;
    }
    const periodKey = periodKeyForMetric(metric, range);
    if (!periodKey) {
      return null;
    }
    return values.find((row) => (
      row
      && typeof row === "object"
      && String(row[periodColumn]) === periodKey
    )) || null;
  }

  function counterValueForRows(rows, metric, range) {
    const valueColumn = metric && (
      metric.value_column
      || Array.isArray(metric.columns) && metric.columns[0]
    );
    const periodKey = periodKeyForMetric(metric, range);
    const row = metric && metric.period_key_column
      ? selectPeriodRow(rows, metric, range)
      : (Array.isArray(rows) && rows.length ? rows[0] : null);
    if (!row) {
      return {
        row: null,
        value: 0,
        valueColumn: valueColumn || "",
        periodKey,
        missing: "key",
      };
    }
    if (
      !valueColumn
      || !Object.prototype.hasOwnProperty.call(row, valueColumn)
      || isNil(row[valueColumn])
    ) {
      return {
        row,
        value: 0,
        valueColumn: valueColumn || "",
        periodKey,
        missing: "column",
      };
    }
    return {
      row,
      value: row[valueColumn],
      valueColumn,
      periodKey,
      missing: "",
    };
  }

  function counterFallbackWarning(state, metric, periodKey, column, reason) {
    const metricId = String(metric && metric.id || "unknown");
    const requestedKey = String(periodKey || state && state.activeRange || "unknown");
    const requestedColumn = String(column || metric && metric.value_column || "unknown");
    const warningId = `${metricId}\u0000${requestedKey}\u0000${requestedColumn}\u0000${reason}`;
    if (state) {
      if (!(state.counterWarnings instanceof Set)) {
        state.counterWarnings = new Set();
      }
      if (state.counterWarnings.has(warningId)) {
        return;
      }
      state.counterWarnings.add(warningId);
    }
    if (root && root.console && typeof root.console.warn === "function") {
      root.console.warn(
        `[Studio counter fallback] metric=${metricId} key=${requestedKey} `
        + `column=${requestedColumn}; displaying 0 (${reason}).`,
      );
    }
  }

  function rowsForMetric(state, metric) {
    const source = rawRowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      return source;
    }
    if (!metric.date_column) {
      return source;
    }
    return filterRowsByRange(source, metric.date_column, state.activeRange);
  }

  function sourceProblem(source) {
    if (source && !Array.isArray(source) && typeof source === "object") {
      return {
        title: source.error || "This generated result is unavailable.",
        message: source.hint || "Review the data source before the next refresh.",
      };
    }
    return {
      title: "This generated result is unavailable.",
      message: "The metric expected a row-based data source.",
    };
  }

  function sparklineGeometry(values, width, height, padding) {
    const numbers = (Array.isArray(values) ? values : [])
      .map(finiteNumber)
      .filter((value) => value !== null);
    if (numbers.length < 2) {
      return null;
    }
    const min = Math.min(...numbers);
    const max = Math.max(...numbers);
    const spread = max - min;
    const usableWidth = width - (padding * 2);
    const usableHeight = height - (padding * 2);
    const points = numbers.map((value, index) => {
      const x = padding + ((index / (numbers.length - 1)) * usableWidth);
      const y = spread === 0
        ? height / 2
        : padding + (((max - value) / spread) * usableHeight);
      return [x, y];
    });
    const line = points
      .map((point, index) => `${index === 0 ? "M" : "L"}${point[0].toFixed(2)},${point[1].toFixed(2)}`)
      .join(" ");
    const area = `${line} L${points[points.length - 1][0].toFixed(2)},${height - padding} L${points[0][0].toFixed(2)},${height - padding} Z`;
    return { points, line, area };
  }

  function appendSparkline(scope, container, values, label) {
    const geometry = sparklineGeometry(values, 240, 64, 4);
    if (!geometry) {
      return;
    }
    const namespace = "http://www.w3.org/2000/svg";
    const svg = scope.createElementNS(namespace, "svg");
    svg.setAttribute("class", "studio-counter-sparkline");
    svg.setAttribute("viewBox", "0 0 240 64");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
    const area = scope.createElementNS(namespace, "path");
    area.setAttribute("class", "studio-sparkline-area");
    area.setAttribute("d", geometry.area);
    const line = scope.createElementNS(namespace, "path");
    line.setAttribute("class", "studio-sparkline-line");
    line.setAttribute("d", geometry.line);
    const last = geometry.points[geometry.points.length - 1];
    const dot = scope.createElementNS(namespace, "circle");
    dot.setAttribute("class", "studio-sparkline-dot");
    dot.setAttribute("cx", last[0].toFixed(2));
    dot.setAttribute("cy", last[1].toFixed(2));
    dot.setAttribute("r", "2.75");
    svg.append(area, line, dot);
    container.appendChild(svg);
  }

  function renderCounter(state, metric) {
    const source = rawRowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    if (!source.length && !metric.period_key_column) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || "No value was returned.",
        "The generated result is valid but contains no rows.",
      );
      return;
    }
    const selected = counterValueForRows(source, metric, state.activeRange);
    const {
      row,
      value,
      valueColumn,
      periodKey,
    } = selected;
    if (selected.missing === "key") {
      counterFallbackWarning(
        state,
        metric,
        periodKey,
        valueColumn,
        "missing period key",
      );
    } else if (selected.missing === "column") {
      counterFallbackWarning(
        state,
        metric,
        periodKey,
        valueColumn,
        "missing metric column or value",
      );
    }
    const body = clearMetricBody(state, metric.id);
    if (!body) {
      return;
    }
    body.dataset.state = "ready";
    const content = createElement(body.ownerDocument, "div", "studio-counter-content");
    content.appendChild(createElement(
      body.ownerDocument,
      "div",
      "studio-counter-value",
      formatValue(value, metric.format, metric),
    ));

    if (
      !metric.compact_counter
      && row
      && metric.comparison_column
      && !isNil(row[metric.comparison_column])
    ) {
      const comparisonValue = finiteNumber(row[metric.comparison_column]) || 0;
      const direction = comparisonValue > 0
        ? "positive"
        : comparisonValue < 0
          ? "negative"
          : "flat";
      const comparison = createElement(
        body.ownerDocument,
        "div",
        `studio-counter-comparison is-${direction}`,
      );
      comparison.appendChild(createElement(
        body.ownerDocument,
        "span",
        "studio-trend-icon",
        direction === "positive" ? "↗" : direction === "negative" ? "↘" : "→",
      ));
      comparison.appendChild(createElement(
        body.ownerDocument,
        "span",
        "",
        `${formatComparison(comparisonValue, metric.comparison_format)} vs prior period`,
      ));
      content.appendChild(comparison);
    }
    if (!metric.compact_counter && metric.context) {
      content.appendChild(createElement(
        body.ownerDocument,
        "p",
        "studio-counter-context",
        metric.context,
      ));
    }
    if (
      !metric.compact_counter
      && metric.sparkline_data_source
      && metric.sparkline_column
    ) {
      const sparklineSource = sourceForMetric(state, metric, metric.sparkline_data_source);
      if (Array.isArray(sparklineSource)) {
        const dateColumn = metric.sparkline_date_column
          || metric.date_column
          || Object.keys(sparklineSource[0] || {}).find((column) => /^(day|date|timestamp)$/i.test(column));
        const filtered = dateColumn
          ? filterRowsByRange(sparklineSource, dateColumn, state.activeRange)
          : sparklineSource;
        appendSparkline(
          body.ownerDocument,
          content,
          filtered.map((item) => item && item[metric.sparkline_column]),
          `${metric.name} trend for ${state.activeRange}`,
        );
      }
    }
    body.appendChild(content);
  }

  function cssValue(state, name, fallback) {
    if (!root || typeof root.getComputedStyle !== "function") {
      return fallback;
    }
    const value = root.getComputedStyle(state.page).getPropertyValue(name).trim();
    return value || fallback;
  }

  function chartTheme(state) {
    return {
      green: cssValue(state, "--studio-green", COLOR_FALLBACKS.green),
      blue: cssValue(state, "--studio-blue", COLOR_FALLBACKS.blue),
      coral: cssValue(state, "--studio-coral", COLOR_FALLBACKS.coral),
      amber: cssValue(state, "--studio-amber", COLOR_FALLBACKS.amber),
      grid: cssValue(state, "--studio-chart-grid", "rgba(120, 130, 140, 0.18)"),
      surface: cssValue(state, "--studio-surface", "#ffffff"),
      ink: cssValue(state, "--studio-ink", "#17221c"),
      muted: cssValue(state, "--studio-muted", "#6e786f"),
    };
  }

  function colorForSeries(theme, color, index) {
    if (color && theme[color]) {
      return theme[color];
    }
    return [theme.green, theme.blue, theme.coral, theme.amber][index % 4];
  }

  function chartContainer(state, metric, kind) {
    const body = clearMetricBody(state, metric.id);
    if (!body) {
      return null;
    }
    body.dataset.state = "ready";
    if (!root || !root.echarts || typeof root.echarts.init !== "function") {
      renderMetricState(
        state,
        metric,
        "error",
        "The chart renderer did not load.",
        "Reload the page to retry the local chart asset.",
      );
      return null;
    }
    const chartElement = createElement(body.ownerDocument, "div", "studio-chart");
    chartElement.dataset.chartKind = kind;
    chartElement.setAttribute("role", "img");
    chartElement.setAttribute("aria-label", `${metric.name} ${kind} chart`);
    body.appendChild(chartElement);
    return chartElement;
  }

  function mountEChart(state, metric, element, option) {
    try {
      const chart = root.echarts.init(element, null, { renderer: "canvas" });
      chart.setOption(option, true);
      state.charts.set(metric.id, chart);
    } catch (error) {
      renderMetricState(
        state,
        metric,
        "error",
        "The chart could not be rendered.",
        error && error.message ? error.message : "Reload the page to try again.",
      );
    }
  }

  function chartAnimationConfig(prefersReducedMotion) {
    return prefersReducedMotion
      ? { animation: false, animationDuration: 0, animationDurationUpdate: 0 }
      : { animation: true, animationDuration: 380, animationDurationUpdate: 260 };
  }

  function reducedMotionPreferred() {
    return Boolean(
      root
      && typeof root.matchMedia === "function"
      && root.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
  }

  function baseChartOption(theme) {
    return {
      ...chartAnimationConfig(reducedMotionPreferred()),
      aria: { enabled: true },
      textStyle: {
        color: theme.ink,
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      },
      tooltip: {
        backgroundColor: theme.surface,
        borderColor: theme.grid,
        borderWidth: 1,
        confine: true,
        extraCssText: "border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.13);",
        textStyle: { color: theme.ink, fontSize: 12 },
      },
    };
  }

  function allowedChartStyles(metric) {
    const configured = Array.isArray(metric && metric.allowed_visualizations)
      ? metric.allowed_visualizations
      : ["line"];
    const allowed = configured.filter((value, index) => (
      CHART_STYLES.includes(value) && configured.indexOf(value) === index
    ));
    return allowed.length ? allowed : ["line"];
  }

  function defaultChartStyle(metric) {
    const allowed = allowedChartStyles(metric);
    return allowed.includes(metric && metric.default_visualization)
      ? metric.default_visualization
      : allowed[0];
  }

  function chartStyleForMetric(state, metric) {
    const selected = state && state.chartStyles && state.chartStyles.get(metric.id);
    return allowedChartStyles(metric).includes(selected)
      ? selected
      : defaultChartStyle(metric);
  }

  function chartPresentation(style) {
    const normalized = CHART_STYLES.includes(style) ? style : "line";
    return {
      style: normalized,
      seriesType: normalized === "column"
        ? "bar"
        : normalized === "scatter"
          ? "scatter"
          : "line",
      boundaryGap: normalized === "column",
      hasArea: normalized === "area",
      isScatter: normalized === "scatter",
    };
  }

  function stableBarInteraction(color, borderRadius) {
    const radius = Array.isArray(borderRadius)
      ? borderRadius.slice()
      : borderRadius;
    const itemStyle = {
      color,
      borderRadius: radius,
    };
    return {
      axisPointer: { type: "none" },
      itemStyle,
      emphasis: {
        focus: "none",
        scale: false,
        itemStyle: {
          ...itemStyle,
          opacity: 1,
          shadowBlur: 5,
          shadowColor: color,
        },
      },
      blur: {
        itemStyle: {
          ...itemStyle,
          opacity: 1,
        },
      },
      select: {
        itemStyle: { ...itemStyle },
      },
    };
  }

  function stackedBarBorderRadius(
    seriesValues,
    seriesIndex,
    dataIndex,
    orientation,
    radius,
  ) {
    const values = Array.isArray(seriesValues) ? seriesValues : [];
    const value = finiteNumber(
      values[seriesIndex] && values[seriesIndex][dataIndex],
    );
    if (value === null || value === 0) {
      return [0, 0, 0, 0];
    }
    const sign = value > 0 ? 1 : -1;
    const isOutermost = !values.slice(seriesIndex + 1).some((series) => {
      const candidate = finiteNumber(series && series[dataIndex]);
      return candidate !== null && candidate !== 0
        && (candidate > 0 ? 1 : -1) === sign;
    });
    if (!isOutermost) {
      return [0, 0, 0, 0];
    }
    const amount = Number.isFinite(Number(radius)) ? Math.max(0, Number(radius)) : 3;
    if (orientation === "horizontal") {
      return sign > 0
        ? [0, amount, amount, 0]
        : [amount, 0, 0, amount];
    }
    return sign > 0
      ? [amount, amount, 0, 0]
      : [0, 0, amount, amount];
  }

  function stackedBarSeriesData(seriesValues, seriesIndex, color, options) {
    const settings = options || {};
    const values = Array.isArray(seriesValues) && Array.isArray(seriesValues[seriesIndex])
      ? seriesValues[seriesIndex]
      : [];
    return values.map((value, dataIndex) => {
      const borderRadius = stackedBarBorderRadius(
        seriesValues,
        seriesIndex,
        dataIndex,
        settings.orientation || "vertical",
        settings.radius,
      );
      const interaction = stableBarInteraction(color, borderRadius);
      return {
        value,
        itemStyle: interaction.itemStyle,
        emphasis: interaction.emphasis,
        blur: interaction.blur,
        select: interaction.select,
      };
    });
  }

  function momentumRowMatches(row, kind) {
    if (!row || typeof row !== "object") {
      return false;
    }
    const recordType = String(row.record_type || "");
    const granularity = String(row.granularity || "");
    if (granularity && granularity !== "daily") {
      return false;
    }
    const expected = {
      cumulative: ["daily_total", "total"],
      activity: ["daily_total", "total"],
      product: ["daily_product", "product"],
      depositor: ["daily_depositor", "depositor", "depositor_type"],
    }[kind] || [];
    return expected.includes(recordType);
  }

  function momentumWeekStart(value) {
    const day = utcStartOfDay(value);
    if (!day) {
      return "";
    }
    const mondayOffset = (day.getUTCDay() + 6) % 7;
    day.setUTCDate(day.getUTCDate() - mondayOffset);
    return day.toISOString().slice(0, 10);
  }

  function momentumNumber(value) {
    if (typeof value === "number") {
      return Number.isFinite(value) ? value : null;
    }
    if (typeof value !== "string" && typeof value !== "bigint") {
      return null;
    }
    const parsed = Number(String(value));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function momentumDecimalText(coefficient, exponent) {
    while (coefficient !== 0n && coefficient % 10n === 0n) {
      coefficient /= 10n;
      exponent += 1;
    }
    const negative = coefficient < 0n;
    const digits = (negative ? -coefficient : coefficient).toString();
    if (digits === "0") {
      return "0";
    }
    const decimalPosition = digits.length + exponent;
    let text;
    if (decimalPosition <= 0) {
      text = `0.${"0".repeat(-decimalPosition)}${digits}`;
    } else if (decimalPosition >= digits.length) {
      text = `${digits}${"0".repeat(decimalPosition - digits.length)}`;
    } else {
      text = `${digits.slice(0, decimalPosition)}.${digits.slice(decimalPosition)}`;
    }
    return negative ? `-${text}` : text;
  }

  function momentumAddDecimals(left, right) {
    const leftParts = decimalStringParts(String(left));
    const rightParts = decimalStringParts(String(right));
    if (
      !leftParts
      || !rightParts
      || leftParts.unsafe
      || rightParts.unsafe
      || !leftParts.coefficient
      || !rightParts.coefficient
    ) {
      return null;
    }
    const exponent = Math.min(leftParts.exponent, rightParts.exponent);
    const leftShift = leftParts.exponent - exponent;
    const rightShift = rightParts.exponent - exponent;
    if (
      leftShift > 10000
      || rightShift > 10000
      || leftParts.coefficient.length + leftShift > 10000
      || rightParts.coefficient.length + rightShift > 10000
    ) {
      return null;
    }
    const leftValue = BigInt(leftParts.coefficient) * (10n ** BigInt(leftShift));
    const rightValue = BigInt(rightParts.coefficient) * (10n ** BigInt(rightShift));
    const total = (leftParts.negative ? -leftValue : leftValue)
      + (rightParts.negative ? -rightValue : rightValue);
    return momentumDecimalText(total, exponent);
  }

  function momentumValueAxisUsesScale(kind, style) {
    const presentation = chartPresentation(style);
    return kind !== "activity"
      && presentation.seriesType !== "bar"
      && !presentation.hasArea;
  }

  function growthChartViews(metric) {
    const config = metric && metric.growth_chart;
    const configured = config && Array.isArray(config.views) ? config.views : [];
    const views = configured.length ? configured : [{ id: "all", label: "All" }];
    return views
      .filter((view) => view && typeof view === "object" && String(view.id || "").trim())
      .map((view) => ({
        ...view,
        id: String(view.id).trim(),
        label: String(view.label || view.id).trim(),
      }));
  }

  function growthChartView(metric, requestedView) {
    const views = growthChartViews(metric);
    const config = metric && metric.growth_chart || {};
    const requested = String(requestedView || config.default_view || "");
    return views.find((view) => view.id === requested) || views[0] || null;
  }

  function growthRecordTypes(config, view, granularity) {
    const mapping = view && view.record_types || config && config.record_types;
    const configured = mapping && typeof mapping === "object" && !Array.isArray(mapping)
      ? mapping[granularity]
      : view && view.record_type || config && config.record_type;
    if (Array.isArray(configured)) {
      const values = configured.map(String).filter(Boolean);
      return values.includes("*") ? [] : values;
    }
    if (configured === "*") {
      return [];
    }
    return configured === null || configured === undefined || configured === ""
      ? []
      : [String(configured)];
  }

  function growthExactValue(value) {
    return momentumAddDecimals("0", value);
  }

  function growthAggregateValue(current, value, aggregation) {
    const exact = growthExactValue(value);
    const numeric = momentumNumber(value);
    if (exact === null || numeric === null) {
      return current;
    }
    if (aggregation === "latest" || !current.present) {
      return { exact, numeric, present: true };
    }
    return {
      exact: momentumAddDecimals(current.exact, exact) || current.exact,
      numeric: current.numeric + numeric,
      present: true,
    };
  }

  function growthSelectedRows(sourceRows, metric, options, view) {
    const config = metric.growth_chart;
    const granularity = options.sourceGranularity
      || options.granularity
      || config.default_granularity
      || "weekly";
    const recordTypes = growthRecordTypes(config, view, granularity);
    const recordTypeColumn = config.record_type_column || "record_type";
    const granularityColumn = config.granularity_column || "granularity";
    const periodColumn = config.period_column || metric.date_column || "period";
    const rangeDateColumn = view.range_date_column
      || config.range_date_column
      || periodColumn;
    const filtered = (Array.isArray(sourceRows) ? sourceRows : []).filter((row) => {
      if (!row || typeof row !== "object") {
        return false;
      }
      if (recordTypes.length && !recordTypes.includes(String(row[recordTypeColumn] || ""))) {
        return false;
      }
      const rowGranularity = String(row[granularityColumn] || "");
      return !rowGranularity || rowGranularity === granularity;
    });
    return filterRowsByRange(
      filtered,
      rangeDateColumn,
      options.activeRange || "ALL",
      options.referenceDate,
    );
  }

  function growthUnitLabel(config, view, format) {
    if (view && view.unit_label || config.unit_label) {
      return String(view && view.unit_label || config.unit_label);
    }
    if (String(format || "").startsWith("currency")) {
      return "Measured in USD";
    }
    if (String(format || "").startsWith("integer")) {
      return "Count";
    }
    return "";
  }

  function growthAxisIndex(value) {
    const normalized = String(value === null || value === undefined ? "" : value)
      .trim()
      .toLocaleLowerCase("en");
    return normalized === "right" || normalized === "1" ? 1 : 0;
  }

  function growthDynamicStackEnabled(model, config, style) {
    if (!model || !model.dynamic) {
      return false;
    }
    const presentation = chartPresentation(style);
    const requested = Boolean(model.stackRequested);
    if (presentation.seriesType === "bar") {
      return Boolean(config && config.stack_columns || requested);
    }
    if (presentation.hasArea) {
      return Boolean(config && config.stack_areas || requested);
    }
    return false;
  }

  function growthTooltipFormat(format) {
    return String(format || "").startsWith("currency")
      ? "currency_compact"
      : format;
  }

  function growthSourceLastUpdated(row) {
    return String(row && (row.last_updated || row.source_last_updated) || "");
  }

  function growthProjectedExportRows(model, config) {
    const columns = Array.isArray(config && config.export_columns)
      ? config.export_columns
      : [];
    const aliases = config && config.export_aliases
      && typeof config.export_aliases === "object"
      ? config.export_aliases
      : {};
    const constants = config && config.export_constants
      && typeof config.export_constants === "object"
      ? config.export_constants
      : {};
    return (model && Array.isArray(model.exportRows) ? model.exportRows : []).map((row) => {
      const projected = {};
      columns.forEach((column) => {
        if (Object.prototype.hasOwnProperty.call(constants, column)) {
          projected[column] = constants[column];
          return;
        }
        const source = aliases[column] || column;
        projected[column] = Object.prototype.hasOwnProperty.call(row, source)
          ? row[source]
          : "";
      });
      return projected;
    });
  }

  function growthVisibleCategorySettings(config, view) {
    const limit = Number(
      view && (view.visible_category_limit || view.visibleCategoryLimit)
      || config && (config.visible_category_limit || config.visibleCategoryLimit)
      || 0,
    );
    const configuredPreserved = view && (
      view.preserve_categories || view.preserveCategories
    ) || config && (
      config.preserve_categories || config.preserveCategories
    );
    return {
      limit: Number.isInteger(limit) && limit > 0 ? limit : 0,
      othersLabel: String(
        view && (view.visible_others_label || view.visibleOthersLabel)
        || config && (config.visible_others_label || config.visibleOthersLabel)
        || "Others",
      ).trim() || "Others",
      preserved: new Set(
        (Array.isArray(configuredPreserved) ? configuredPreserved : [])
          .map((value) => String(value || "").trim())
          .filter(Boolean),
      ),
      rankByMagnitude: Boolean(
        view && (view.rank_by_activity_magnitude || view.rankByActivityMagnitude)
        || config && (config.rank_by_activity_magnitude || config.rankByActivityMagnitude),
      ),
      preserveUncategorized: Boolean(
        view && (
          view.preserve_uncategorized_when_material
          || view.preserveUncategorizedWhenMaterial
        )
        || config && (
          config.preserve_uncategorized_when_material
          || config.preserveUncategorizedWhenMaterial
        ),
      ),
    };
  }

  function growthRankingVisibleRows(rankedRowsValue, settings) {
    const ranked = Array.isArray(rankedRowsValue) ? rankedRowsValue : [];
    if (!settings || !settings.limit) {
      return { rows: ranked.slice(), visibleName: (name) => name };
    }
    const isPreserved = (row) => (
      settings.preserved.has(row.name)
      || (
        settings.preserveUncategorized
        && row.name === "Uncategorized"
        && Math.abs(Number(row.numeric) || 0) > 0
      )
    );
    const preservedRows = ranked.filter(isPreserved);
    const activeRows = ranked.filter((row) => !isPreserved(row));
    const selected = activeRows.slice(0, settings.limit);
    const selectedNames = new Set(selected.map((row) => row.name));
    const remainder = activeRows.slice(settings.limit);
    let othersExact = "0";
    let othersNumeric = 0;
    let othersLastUpdated = "";
    remainder.forEach((row) => {
      othersExact = momentumAddDecimals(othersExact, row.exact) || othersExact;
      othersNumeric += Number(row.numeric) || 0;
      othersLastUpdated = row.sourceLastUpdated || othersLastUpdated;
    });
    const visible = selected.slice();
    if (remainder.length) {
      visible.push({
        name: settings.othersLabel,
        exact: othersExact,
        numeric: othersNumeric,
        present: true,
        sourceLastUpdated: othersLastUpdated,
        groupedCategoryCount: remainder.length,
      });
    }
    visible.push(...preservedRows);
    return {
      rows: visible,
      visibleName(name) {
        return selectedNames.has(name)
          || settings.preserved.has(name)
          || settings.preserveUncategorized && name === "Uncategorized"
          ? name
          : settings.othersLabel;
      },
    };
  }

  function growthDynamicCategoryPlan(groupedRows, valueColumn, settings) {
    const rows = Array.isArray(groupedRows) ? groupedRows : [];
    const allCategories = orderedMomentumValues(rows.map((row) => row.dimension));
    if (!settings || !settings.limit) {
      return { categories: allCategories, visibleName: (name) => name };
    }
    const magnitude = new Map();
    rows.forEach((row) => {
      const value = row.values && row.values[valueColumn];
      const numeric = value && value.present ? Number(value.numeric) : 0;
      magnitude.set(
        row.dimension,
        (magnitude.get(row.dimension) || 0)
          + (settings.rankByMagnitude ? Math.abs(numeric) : numeric),
      );
    });
    const preserved = allCategories.filter((name) => settings.preserved.has(name));
    const ranked = allCategories
      .filter((name) => !settings.preserved.has(name))
      .sort((left, right) => (
        (magnitude.get(right) || 0) - (magnitude.get(left) || 0)
        || left.localeCompare(right, "en", { sensitivity: "base" })
      ));
    const selected = ranked.slice(0, settings.limit);
    const selectedSet = new Set(selected);
    const hasOthers = ranked.length > selected.length;
    return {
      categories: [
        ...selected,
        ...(hasOthers ? [settings.othersLabel] : []),
        ...preserved,
      ],
      visibleName(name) {
        return selectedSet.has(name) || settings.preserved.has(name)
          ? name
          : settings.othersLabel;
      },
    };
  }

  function growthChartModel(sourceRows, metric, options) {
    const config = metric && metric.growth_chart;
    if (!config) {
      return null;
    }
    const selection = options || {};
    const kind = String(config.kind || "timeseries");
    const granularity = kind === "ranking" ? "total" : String(
      selection.granularity || config.default_granularity || "weekly",
    );
    const view = growthChartView(metric, selection.view);
    if (!view) {
      return null;
    }
    const latestPeriodOnly = kind === "ranking" && Boolean(
      view.latest_period_only || config.latest_period_only,
    );
    const rebuildWeekly = granularity === "weekly" && Boolean(
      view.rebuild_weekly_from_daily || config.rebuild_weekly_from_daily,
    );
    const sourceGranularity = rebuildWeekly ? "daily" : granularity;
    const periodColumn = config.period_column || metric.date_column || "period";
    const orderColumn = view.range_date_column
      || config.range_date_column
      || periodColumn;
    let rows = growthSelectedRows(sourceRows, metric, {
      ...selection,
      granularity,
      sourceGranularity,
      activeRange: latestPeriodOnly ? "ALL" : selection.activeRange,
    }, view).sort((left, right) => (
      String(left && left[orderColumn] || "")
        .localeCompare(String(right && right[orderColumn] || ""))
    ));
    let latestPeriod = "";
    if (latestPeriodOnly) {
      latestPeriod = rows.reduce((current, row) => {
        const candidate = String(row && row[periodColumn] || "").trim();
        if (!candidate) {
          return current;
        }
        const currentDate = parseDate(current);
        const candidateDate = parseDate(candidate);
        if (candidateDate && (!currentDate || candidateDate > currentDate)) {
          return candidate;
        }
        if (!candidateDate && !currentDate && candidate.localeCompare(current) > 0) {
          return candidate;
        }
        return current;
      }, "");
      rows = latestPeriod
        ? rows.filter((row) => (
          String(row && row[periodColumn] || "").trim() === latestPeriod
        ))
        : [];
    }
    const dimensionColumn = view.dimension_column || config.dimension_column || "";
    const valueColumnMapping = view.value_column_by_granularity
      || config.value_column_by_granularity;
    const valueColumn = valueColumnMapping && valueColumnMapping[sourceGranularity]
      || view.value_column
      || config.value_column
      || metric.value_column
      || "";
    const configuredMeasures = Array.isArray(view.measures) && view.measures.length
      ? view.measures
      : Array.isArray(config.measures) ? config.measures : [];
    const measures = configuredMeasures.map((measure) => ({
      ...measure,
      column: measure.column_by_granularity
        && measure.column_by_granularity[sourceGranularity]
        || measure.column,
    }));
    const aggregation = view.aggregation || config.aggregation || "sum";
    const activeRange = String(selection.activeRange || "ALL");
    const selectedView = view.id;
    const periodForRow = (row) => {
      const sourcePeriod = String(row && row[periodColumn] || "").trim();
      return rebuildWeekly ? momentumWeekStart(sourcePeriod) : sourcePeriod;
    };
    const baseExportRow = (sourceLastUpdated) => ({
      granularity,
      source_granularity: granularity === "weekly"
        ? "week"
        : granularity === "daily" ? "day" : granularity,
      selected_view: selectedView,
      dashboard_period: activeRange,
      source_last_updated: sourceLastUpdated || "",
    });
    const contextFormat = view.format
      || config.format
      || measures[0] && measures[0].format
      || metric.format;
    const context = [
      kind === "ranking" ? (
        latestPeriodOnly ? "Latest source day" : `${activeRange} dashboard period`
      ) : (
        granularity === "weekly" ? "Weekly" : "Daily"
      ),
      growthChartViews(metric).length > 1 || config.show_view_context
        ? view.label
        : "",
      growthUnitLabel(config, view, contextFormat),
    ].filter(Boolean).join(" · ");
    const visibleCategorySettings = growthVisibleCategorySettings(config, view);

    if (kind === "ranking") {
      const grouped = new Map();
      rows.forEach((row) => {
        const dimension = String(row && row[dimensionColumn] || "").trim();
        if (!dimension || !valueColumn) {
          return;
        }
        const current = grouped.get(dimension) || {
          exact: "0",
          numeric: 0,
          present: false,
        };
        const value = growthAggregateValue(current, row[valueColumn], aggregation);
        grouped.set(dimension, {
          ...value,
          sourceLastUpdated: growthSourceLastUpdated(row) || current.sourceLastUpdated || "",
        });
      });
      const ranked = Array.from(grouped, ([name, value]) => ({ name, ...value }))
        .filter((row) => row.present)
        .sort((left, right) => compareValues(right.exact, left.exact));
      const configuredRanking = Number(config.limit) > 0
        ? ranked.slice(0, Number(config.limit))
        : ranked;
      const visibleRanking = growthRankingVisibleRows(
        configuredRanking,
        visibleCategorySettings,
      );
      const ranking = visibleRanking.rows;
      return {
        categories: ranking.map((row) => row.name),
        context,
        exportRows: configuredRanking.map((row) => ({
          ...baseExportRow(row.sourceLastUpdated),
          ...(latestPeriodOnly ? {
            [periodColumn]: latestPeriod,
            period: latestPeriod,
          } : {}),
          [dimensionColumn]: row.name,
          [valueColumn]: row.exact,
          dimension: row.name,
          raw_category: row.name,
          visible_category: visibleRanking.visibleName(row.name),
          primary_value: row.exact,
          secondary_value: "",
        })),
        granularity,
        kind,
        periods: [],
        ranking,
        rows,
        selectedView,
        series: [{
          axis: 0,
          color: view.color || config.color || "green",
          format: view.format || config.format || metric.format,
          name: view.series_label || config.series_label || metric.name,
          type: "bar",
          values: ranking.map((row) => row.numeric),
        }],
        view,
        views: growthChartViews(metric),
      };
    }

    const grouped = new Map();
    const dynamic = Boolean(dimensionColumn && valueColumn);
    rows.forEach((row) => {
      const period = periodForRow(row);
      const dimension = dynamic ? String(row && row[dimensionColumn] || "").trim() : "";
      if (!period || dynamic && !dimension) {
        return;
      }
      const key = `${period}\u0000${dimension}`;
      const current = grouped.get(key) || {
        period,
        dimension,
        sourceLastUpdated: "",
        values: {},
      };
      const selectedMeasures = dynamic
        ? [{ column: valueColumn }]
        : measures;
      selectedMeasures.forEach((measure) => {
        const column = String(measure && measure.column || "");
        if (!column) {
          return;
        }
        current.values[column] = growthAggregateValue(
          current.values[column] || { exact: "0", numeric: 0, present: false },
          row[column],
          measure.aggregation || aggregation,
        );
      });
      current.sourceLastUpdated = growthSourceLastUpdated(row)
        || current.sourceLastUpdated;
      grouped.set(key, current);
    });
    const groupedRows = Array.from(grouped.values()).sort((left, right) => (
      left.period.localeCompare(right.period)
      || left.dimension.localeCompare(right.dimension, "en", { sensitivity: "base" })
    ));
    const periods = Array.from(new Set(groupedRows.map((row) => row.period))).sort();
    const valueByKey = new Map(groupedRows.map((row) => (
      [`${row.period}\u0000${row.dimension}`, row]
    )));
    let series;
    const exportRows = [];
    const dynamicMeasure = measures[0] || {};
    const stackRequested = Boolean(dynamicMeasure.stack);
    if (dynamic) {
      const categoryPlan = growthDynamicCategoryPlan(
        groupedRows,
        valueColumn,
        visibleCategorySettings,
      );
      const categories = categoryPlan.categories;
      series = categories.map((name, index) => ({
        axis: growthAxisIndex(dynamicMeasure.axis),
        color: "",
        format: view.format || config.format || dynamicMeasure.format || metric.format,
        name,
        type: "dynamic",
        values: periods.map((period) => {
          if (name !== visibleCategorySettings.othersLabel) {
            const row = valueByKey.get(`${period}\u0000${name}`);
            const value = row && row.values[valueColumn];
            return value && value.present ? value.numeric : 0;
          }
          return groupedRows.reduce((total, row) => {
            if (
              row.period !== period
              || categoryPlan.visibleName(row.dimension)
                !== visibleCategorySettings.othersLabel
            ) {
              return total;
            }
            const value = row.values && row.values[valueColumn];
            return total + (value && value.present ? value.numeric : 0);
          }, 0);
        }),
      }));
      groupedRows.forEach((row) => {
        const value = row.values[valueColumn];
        if (!value || !value.present) {
          return;
        }
        exportRows.push({
          ...baseExportRow(row.sourceLastUpdated),
          [periodColumn]: row.period,
          [dimensionColumn]: row.dimension,
          [valueColumn]: value.exact,
          dimension: row.dimension,
          raw_category: row.dimension,
          visible_category: categoryPlan.visibleName(row.dimension),
          primary_value: value.exact,
          secondary_value: "",
        });
      });
    } else {
      series = measures.map((measure, index) => ({
        axis: growthAxisIndex(measure.axis),
        color: measure.color || "",
        format: measure.format || metric.format,
        name: measure.label || measure.column,
        scale: typeof measure.scale === "boolean" ? measure.scale : undefined,
        stack: measure.stack || "",
        type: measure.series_type || "dynamic",
        values: periods.map((period) => {
          const row = valueByKey.get(`${period}\u0000`);
          const value = row && row.values[measure.column];
          return value && value.present ? value.numeric : 0;
        }),
      }));
      periods.forEach((period) => {
        const row = valueByKey.get(`${period}\u0000`);
        const projected = {
          ...baseExportRow(row && row.sourceLastUpdated),
          [periodColumn]: period,
          dimension: "",
          primary_value: "0",
          secondary_value: "",
        };
        measures.forEach((measure) => {
          const value = row && row.values[measure.column];
          projected[measure.column] = value && value.present ? value.exact : "0";
        });
        const primary = row && row.values[measures[0] && measures[0].column];
        const secondary = row && row.values[measures[1] && measures[1].column];
        projected.primary_value = primary && primary.present ? primary.exact : "0";
        projected.secondary_value = secondary && secondary.present
          ? secondary.exact
          : "";
        exportRows.push(projected);
      });
    }
    return {
      categories: dynamic ? series.map((item) => item.name) : [],
      context,
      dynamic,
      exportRows,
      granularity,
      kind,
      periods,
      rows,
      selectedView,
      series,
      stackRequested,
      view,
      views: growthChartViews(metric),
    };
  }

  function orderedMomentumValues(values, preferredOrder) {
    const unique = Array.from(new Set(
      (Array.isArray(values) ? values : [])
        .map((value) => String(value || "").trim())
        .filter(Boolean),
    ));
    const preferred = Array.isArray(preferredOrder) ? preferredOrder : [];
    const preferredSet = new Set(preferred);
    return [
      ...preferred.filter((value) => unique.includes(value)),
      ...unique.filter((value) => !preferredSet.has(value)).sort((left, right) => (
        left.localeCompare(right, "en", { sensitivity: "base" })
      )),
    ];
  }

  function momentumFilterOptions(sourceRows, metric) {
    const config = metric && metric.momentum_chart;
    if (!config || !config.filter_column) {
      return [];
    }
    const kind = config.kind;
    const values = (Array.isArray(sourceRows) ? sourceRows : [])
      .filter((row) => momentumRowMatches(row, kind))
      .map((row) => row && row[config.filter_column]);
    return orderedMomentumValues(values, config.filter_order);
  }

  function periodsSpanYears(values) {
    const years = new Set(
      (Array.isArray(values) ? values : [])
        .map((value) => parseDate(value))
        .filter(Boolean)
        .map((value) => value.getUTCFullYear()),
    );
    return years.size > 1;
  }

  function chartPeriodLabel(value, granularity, options) {
    const settings = options || {};
    const label = settings.includeYear ? longDate(value) : shortDate(value);
    return granularity === "weekly" && settings.tooltip && label
      ? `Week of ${label}`
      : label;
  }

  function momentumChartModel(sourceRows, metric, options) {
    const config = metric && metric.momentum_chart;
    if (!config) {
      return null;
    }
    const selection = options || {};
    const granularity = selection.granularity === "weekly" ? "weekly" : "daily";
    const selectedFilter = String(selection.filter || "all");
    const filterColumn = config.filter_column || "";
    const dailyRows = (Array.isArray(sourceRows) ? sourceRows : [])
      .filter((row) => momentumRowMatches(row, config.kind));
    const rangedRows = filterRowsByRange(
      dailyRows,
      "period",
      selection.activeRange || "ALL",
      selection.referenceDate,
    ).filter((row) => (
      !filterColumn
      || selectedFilter === "all"
      || String(row && row[filterColumn]) === selectedFilter
    ));
    const grouped = new Map();
    rangedRows.forEach((row) => {
      const sourcePeriod = row && (row.period || row.day);
      const period = granularity === "weekly"
        ? momentumWeekStart(sourcePeriod)
        : String(sourcePeriod || "");
      if (!period) {
        return;
      }
      const dimension = filterColumn ? String(row[filterColumn] || "") : "";
      if (filterColumn && !dimension) {
        return;
      }
      const key = `${period}\u0000${dimension}`;
      const current = grouped.get(key) || {
        period,
        dimension,
        amount_usd: 0,
        amount_usd_exact: "0",
        num_deposits: 0,
      };
      const amount = momentumNumber(row.amount_usd);
      const exactAmount = momentumAddDecimals(current.amount_usd_exact, row.amount_usd);
      const deposits = momentumNumber(row.num_deposits);
      if (amount !== null) {
        current.amount_usd += amount;
      }
      if (exactAmount !== null) {
        current.amount_usd_exact = exactAmount;
      }
      if (deposits !== null) {
        current.num_deposits += deposits;
      }
      grouped.set(key, current);
    });
    const groupedRows = Array.from(grouped.values()).sort((left, right) => (
      left.period.localeCompare(right.period)
      || left.dimension.localeCompare(right.dimension, "en", { sensitivity: "base" })
    ));
    const periods = Array.from(new Set(groupedRows.map((row) => row.period))).sort();
    const filterOptions = momentumFilterOptions(dailyRows, metric);
    const allSelected = !filterColumn || selectedFilter === "all";
    let seriesNames = filterColumn
      ? orderedMomentumValues(
          groupedRows.map((row) => row.dimension),
          config.filter_order,
        )
      : [config.kind === "activity" ? "Referral deposits" : "Cumulative deposits"];
    if (filterColumn) {
      seriesNames = seriesNames.filter((name) => groupedRows.some((row) => (
        row.dimension === name
        && (config.kind === "activity" ? row.num_deposits : row.amount_usd) !== 0
      )));
    }
    const valueByKey = new Map(groupedRows.map((row) => (
      [`${row.period}\u0000${row.dimension}`, row]
    )));
    const exportRows = [];
    let series = [];
    if (config.kind === "cumulative") {
      let running = 0;
      let runningExact = "0";
      const values = periods.map((period) => {
        const row = valueByKey.get(`${period}\u0000`) || {
          amount_usd: 0,
          amount_usd_exact: "0",
        };
        running += row.amount_usd;
        runningExact = momentumAddDecimals(runningExact, row.amount_usd_exact)
          || runningExact;
        exportRows.push({
          period,
          period_deposits_usd: row.amount_usd_exact,
          cumulative_deposits_usd: runningExact,
          granularity,
        });
        return running;
      });
      series = [{ name: "Cumulative deposits", values }];
    } else if (config.kind === "activity") {
      const values = periods.map((period) => {
        const row = valueByKey.get(`${period}\u0000`) || { num_deposits: 0 };
        const count = Math.round(row.num_deposits);
        exportRows.push({ period, num_deposits: count, granularity });
        return count;
      });
      series = [{ name: "Referral deposits", values }];
    } else {
      series = seriesNames.map((name) => ({
        name,
        values: periods.map((period) => {
          const row = valueByKey.get(`${period}\u0000${name}`);
          return row ? row.amount_usd : 0;
        }),
      }));
      groupedRows.forEach((row) => {
        if (config.kind === "product") {
          exportRows.push({
            period: row.period,
            strategy_symbol: row.dimension,
            amount_usd: row.amount_usd_exact,
            granularity,
            selected_product: allSelected ? "All" : selectedFilter,
          });
        } else {
          exportRows.push({
            period: row.period,
            new_or_old: row.dimension,
            amount_usd: row.amount_usd_exact,
            granularity,
            selected_classification: allSelected ? "All" : selectedFilter,
          });
        }
      });
    }
    const selectionLabel = filterColumn
      ? (allSelected ? config.all_label : selectedFilter)
      : "";
    const context = [
      granularity === "weekly" ? "Weekly" : "Daily",
      selectionLabel,
      config.kind === "activity" ? "Number of deposits" : "Measured in USD",
    ].filter(Boolean).join(" · ");
    return {
      allSelected,
      context,
      exportRows,
      filterOptions,
      granularity,
      periods,
      selectedFilter,
      series,
      shouldStack: allSelected && ["product", "depositor"].includes(config.kind),
    };
  }

  function ensureMomentumFilterOptions(state, metric, source) {
    const select = state.page.querySelector(`[data-momentum-filter="${metric.id}"]`);
    if (!select) {
      return;
    }
    const config = metric.momentum_chart;
    const selection = state.momentumSelections.get(metric.id);
    const values = momentumFilterOptions(source, metric);
    const desired = ["all", ...values];
    const current = Array.from(select.options).map((option) => option.value);
    if (current.length !== desired.length || current.some((value, index) => value !== desired[index])) {
      select.replaceChildren();
      desired.forEach((value) => {
        const option = select.ownerDocument.createElement("option");
        option.value = value;
        option.textContent = value === "all" ? config.all_label : value;
        select.appendChild(option);
      });
    }
    const selected = values.includes(selection.filter) ? selection.filter : "all";
    selection.filter = selected;
    select.value = selected;
  }

  function renderMomentumChart(state, metric) {
    const source = rawRowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    ensureMomentumFilterOptions(state, metric, source);
    const selection = state.momentumSelections.get(metric.id) || {
      granularity: metric.momentum_chart.default_granularity,
      filter: "all",
    };
    const model = momentumChartModel(source, metric, {
      ...selection,
      activeRange: state.activeRange,
      referenceDate: state.referenceDate,
    });
    const context = state.page.querySelector(`[data-momentum-context="${metric.id}"]`);
    if (context && model) {
      context.textContent = model.context;
    }
    if (!model || !model.periods.length || !model.series.length) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || "No chartable values fall within this selection.",
        "Choose another range, granularity, or data filter.",
      );
      return;
    }
    const chartStyle = chartStyleForMetric(state, metric);
    const presentation = chartPresentation(chartStyle);
    const isColumn = presentation.seriesType === "bar";
    const isScatter = presentation.isScatter;
    const element = chartContainer(state, metric, chartStyle);
    if (!element) {
      return;
    }
    const theme = chartTheme(state);
    const config = metric.momentum_chart;
    const stackSeries = model.shouldStack && (isColumn || presentation.hasArea);
    const option = {
      ...baseChartOption(theme),
      color: model.series.map((series, index) => colorForSeries(theme, "", index)),
      grid: {
        top: model.series.length > 1 ? 48 : 20,
        right: 18,
        bottom: 42,
        left: 70,
        containLabel: false,
      },
      legend: model.series.length > 1 ? {
        top: 2,
        left: 4,
        icon: "roundRect",
        itemWidth: 16,
        itemHeight: 3,
        textStyle: { color: theme.muted, fontSize: 11 },
      } : undefined,
      tooltip: {
        ...baseChartOption(theme).tooltip,
        trigger: "axis",
        axisPointer: isColumn
          ? { type: "shadow", shadowStyle: { color: theme.grid, opacity: 0.3 } }
          : { type: "line", lineStyle: { color: theme.grid } },
        formatter(params) {
          const points = Array.isArray(params) ? params : [params];
          const period = points.length ? points[0].axisValue : "";
          const title = chartPeriodLabel(period, model.granularity, {
            includeYear: true,
            tooltip: true,
          });
          const rowsHtml = points.map((point) => {
            const formatted = formatTooltipValue(
              point.value,
              config.kind === "activity" ? "integer" : "currency_compact",
              metric,
            );
            return `<div style="display:flex;gap:18px;justify-content:space-between;margin-top:5px">`
              + `<span>${point.marker || ""}${escapeHtml(point.seriesName)}</span>`
              + `<strong>${escapeHtml(formatted)}</strong></div>`;
          }).join("");
          return `<strong>${escapeHtml(title)}</strong>${rowsHtml}`;
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: presentation.boundaryGap,
        data: model.periods,
        axisLine: { lineStyle: { color: theme.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: theme.muted,
          hideOverlap: true,
          margin: 14,
          formatter: (value) => chartPeriodLabel(value, model.granularity, {
            includeYear: model.granularity === "weekly"
              && periodsSpanYears(model.periods),
          }),
        },
      },
      yAxis: {
        type: "value",
        scale: momentumValueAxisUsesScale(config.kind, chartStyle),
        minInterval: config.kind === "activity" ? 1 : undefined,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.muted,
          formatter: (value) => formatAxisValue(value, metric),
        },
        splitLine: { lineStyle: { color: theme.grid, type: "dashed" } },
      },
      series: model.series.map((series, index) => {
        const color = colorForSeries(theme, "", index);
        const barInteraction = stableBarInteraction(color, [3, 3, 0, 0]);
        const stackedData = isColumn && stackSeries
          ? stackedBarSeriesData(
            model.series.map((item) => item.values),
            index,
            color,
            { orientation: "vertical", radius: 3 },
          )
          : null;
        return {
          name: series.name,
          type: presentation.seriesType,
          data: stackedData || series.values,
          stack: stackSeries ? "momentum-total" : undefined,
          stackStrategy: stackSeries && isColumn ? "samesign" : undefined,
          smooth: isColumn || isScatter ? false : 0.18,
          showSymbol: isScatter ? true : isColumn ? undefined : false,
          symbolSize: isScatter ? 8 : undefined,
          connectNulls: false,
          lineStyle: isColumn || isScatter ? undefined : { width: 2.2 },
          barMaxWidth: isColumn ? 24 : undefined,
          itemStyle: isColumn && !stackedData ? barInteraction.itemStyle : { color },
          areaStyle: presentation.hasArea ? {
            opacity: model.series.length === 1 ? 0.16 : 0.11,
            color,
          } : undefined,
          emphasis: isColumn && !stackedData
            ? barInteraction.emphasis
            : isColumn ? undefined : { focus: "series" },
          blur: isColumn && !stackedData ? barInteraction.blur : undefined,
          select: isColumn && !stackedData ? barInteraction.select : undefined,
        };
      }),
    };
    mountEChart(state, metric, element, option);
  }

  function growthAxisUsesScale(series, style) {
    const configured = series.find((item) => typeof item.scale === "boolean");
    if (configured) {
      return configured.scale;
    }
    const format = String(series[0] && series[0].format || "");
    const presentation = chartPresentation(style);
    return !format.startsWith("integer")
      && !presentation.hasArea
      && series.every((item) => item.renderedType !== "bar");
  }

  function renderGrowthChart(state, metric) {
    const source = rawRowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    const config = metric.growth_chart;
    const selection = state.growthSelections.get(metric.id) || {
      granularity: config.default_granularity || "weekly",
      view: config.default_view || growthChartViews(metric)[0] && growthChartViews(metric)[0].id,
    };
    const model = growthChartModel(source, metric, {
      ...selection,
      activeRange: state.activeRange,
      referenceDate: state.referenceDate,
    });
    if (
      !model
      || model.kind === "ranking" && !model.ranking.length
      || model.kind !== "ranking" && (!model.periods.length || !model.series.length)
    ) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || "No chartable values fall within this selection.",
        "Choose another dashboard period or chart control.",
      );
      return;
    }
    const chartStyle = metric.visualization_type === "line"
      ? chartStyleForMetric(state, metric)
      : "column";
    const presentation = chartPresentation(chartStyle);
    const theme = chartTheme(state);
    const element = chartContainer(
      state,
      metric,
      model.kind === "ranking" ? "bar" : chartStyle,
    );
    if (!element) {
      return;
    }

    if (model.kind === "ranking") {
      const seriesConfig = model.series[0];
      const color = colorForSeries(theme, seriesConfig.color, 0);
      const interaction = stableBarInteraction(color, [0, 4, 4, 0]);
      const option = {
        ...baseChartOption(theme),
        grid: { top: 16, right: 34, bottom: 36, left: 112, containLabel: false },
        tooltip: {
          ...baseChartOption(theme).tooltip,
          trigger: "item",
          formatter(point) {
            return `<strong>${escapeHtml(point.name)}</strong>`
              + `<div style="margin-top:5px">${escapeHtml(formatTooltipValue(
              point.value,
                growthTooltipFormat(seriesConfig.format),
                metric,
              ))}</div>`;
          },
        },
        xAxis: {
          type: "value",
          min: 0,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: theme.muted,
            formatter: (value) => formatAxisValue(value, {
              ...metric,
              format: seriesConfig.format,
            }),
          },
          splitLine: { lineStyle: { color: theme.grid, type: "dashed" } },
        },
        yAxis: {
          type: "category",
          inverse: true,
          data: model.categories,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: theme.muted, width: 100, overflow: "truncate" },
        },
        series: [{
          name: seriesConfig.name,
          type: "bar",
          data: seriesConfig.values,
          barMaxWidth: 18,
          itemStyle: interaction.itemStyle,
          emphasis: interaction.emphasis,
          blur: interaction.blur,
          select: interaction.select,
        }],
      };
      mountEChart(state, metric, element, option);
      return;
    }

    const dynamicType = presentation.seriesType;
    const renderedSeries = model.series.map((series) => ({
      ...series,
      renderedType: series.type === "dynamic"
        ? dynamicType
        : series.type === "column" ? "bar"
          : series.type === "area" ? "line" : series.type,
    }));
    const hasBars = renderedSeries.some((series) => series.renderedType === "bar");
    const hasArea = presentation.hasArea && renderedSeries.some((series) => (
      series.type === "dynamic" || series.type === "area"
    ));
    const stackDynamic = growthDynamicStackEnabled(model, config, chartStyle);
    const stackKeyForSeries = (series) => (
      model.dynamic
        ? (stackDynamic ? "growth-total" : "")
        : series.stack === true ? "growth-total" : series.stack || ""
    );
    const maxAxis = Math.max(0, ...renderedSeries.map((series) => (
      growthAxisIndex(series.axis)
    )));
    const yAxes = Array.from({ length: maxAxis + 1 }, (_, axisIndex) => {
      const axisSeries = renderedSeries.filter((series) => (
        growthAxisIndex(series.axis) === axisIndex
      ));
      const format = axisSeries[0] && axisSeries[0].format || metric.format;
      const axisTitle = maxAxis > 0 && axisSeries.length
        ? `${axisSeries[0].name}${String(format).startsWith("currency") ? " in USD" : ""}`
        : "";
      return {
        type: "value",
        position: axisIndex === 1 ? "right" : "left",
        name: axisTitle,
        nameLocation: "middle",
        nameGap: axisIndex === 1 ? 60 : 56,
        nameRotate: axisIndex === 1 ? -90 : 90,
        nameTextStyle: { color: theme.muted, fontSize: 9, fontWeight: 650 },
        scale: growthAxisUsesScale(axisSeries, chartStyle),
        minInterval: String(format).startsWith("integer") ? 1 : undefined,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.muted,
          formatter: (value) => formatAxisValue(value, { ...metric, format }),
        },
        splitLine: axisIndex === 0
          ? { lineStyle: { color: theme.grid, type: "dashed" } }
          : { show: false },
      };
    });
    const option = {
      ...baseChartOption(theme),
      color: renderedSeries.map((series, index) => (
        colorForSeries(theme, series.color, index)
      )),
      grid: {
        top: renderedSeries.length > 1 ? 45 : 17,
        right: maxAxis > 0 ? 72 : 18,
        bottom: 39,
        left: 68,
        containLabel: false,
      },
      legend: renderedSeries.length > 1 ? {
        type: "scroll",
        top: 1,
        left: 4,
        right: 4,
        icon: "roundRect",
        itemWidth: 14,
        itemHeight: 3,
        textStyle: { color: theme.muted, fontSize: 10 },
      } : undefined,
      tooltip: {
        ...baseChartOption(theme).tooltip,
        trigger: "axis",
        axisPointer: hasBars
          ? { type: "shadow", shadowStyle: { color: theme.grid, opacity: 0.26 } }
          : { type: "line", lineStyle: { color: theme.grid } },
        formatter(params) {
          const points = Array.isArray(params) ? params : [params];
          const title = points.length
            ? chartPeriodLabel(points[0].axisValue, model.granularity, {
              includeYear: true,
              tooltip: true,
            })
            : "";
          const nonzeroPoints = metric.tooltip_signed
            ? points.filter((point) => Number(point.value) !== 0)
            : points;
          const displayPoints = nonzeroPoints.length ? nonzeroPoints : points;
          const rowsHtml = displayPoints.map((point) => {
            const series = renderedSeries[Number(point.seriesIndex)] || renderedSeries[0];
            return `<div style="display:flex;gap:18px;justify-content:space-between;margin-top:5px">`
              + `<span>${point.marker || ""}${escapeHtml(point.seriesName)}</span>`
              + `<strong>${escapeHtml(formatTooltipValue(
                point.value,
                growthTooltipFormat(series && series.format || metric.format),
                metric,
              ))}</strong></div>`;
          }).join("");
          return `<strong>${escapeHtml(title)}</strong>${rowsHtml}`;
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: hasBars,
        data: model.periods,
        axisLine: { lineStyle: { color: theme.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: theme.muted,
          hideOverlap: true,
          margin: 12,
          formatter: (value) => chartPeriodLabel(value, model.granularity, {
            includeYear: model.granularity === "weekly"
              && periodsSpanYears(model.periods),
          }),
        },
      },
      yAxis: yAxes.length === 1 ? yAxes[0] : yAxes,
      series: renderedSeries.map((series, index) => {
        const color = colorForSeries(theme, series.color, index);
        const isBar = series.renderedType === "bar";
        const interaction = stableBarInteraction(color, [3, 3, 0, 0]);
        const stackKey = stackKeyForSeries(series);
        const stackIndexes = isBar && stackKey
          ? renderedSeries
            .map((candidate, candidateIndex) => ({ candidate, candidateIndex }))
            .filter(({ candidate }) => (
              candidate.renderedType === "bar"
              && stackKeyForSeries(candidate) === stackKey
            ))
            .map(({ candidateIndex }) => candidateIndex)
          : [];
        const stackIndex = stackIndexes.indexOf(index);
        const stackedData = stackIndex >= 0
          ? stackedBarSeriesData(
            stackIndexes.map((candidateIndex) => renderedSeries[candidateIndex].values),
            stackIndex,
            color,
            { orientation: "vertical", radius: 3 },
          )
          : null;
        const area = presentation.hasArea && (
          series.type === "dynamic" || series.type === "area"
        );
        return {
          name: series.name,
          type: series.renderedType,
          yAxisIndex: growthAxisIndex(series.axis),
          data: stackedData || series.values,
          stack: stackKey || undefined,
          stackStrategy: isBar && stackKey ? "samesign" : undefined,
          smooth: isBar ? false : 0.18,
          showSymbol: isBar ? undefined : false,
          connectNulls: false,
          lineStyle: isBar ? undefined : { width: 2.1 },
          barMaxWidth: isBar ? 22 : undefined,
          itemStyle: isBar && !stackedData ? interaction.itemStyle : { color },
          areaStyle: area ? {
            opacity: renderedSeries.length === 1 ? 0.16 : 0.1,
            color,
          } : undefined,
          emphasis: isBar && !stackedData
            ? interaction.emphasis
            : isBar ? undefined : { focus: "series" },
          blur: isBar && !stackedData ? interaction.blur : undefined,
          select: isBar && !stackedData ? interaction.select : undefined,
        };
      }),
    };
    mountEChart(state, metric, element, option);
  }

  function renderLineChart(state, metric) {
    if (metric.momentum_chart) {
      renderMomentumChart(state, metric);
      return;
    }
    if (metric.growth_chart) {
      renderGrowthChart(state, metric);
      return;
    }
    const source = rowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    if (!source.length) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || (
          sourceForMetric(state, metric).length
            ? "No rows fall within this date range."
            : "No rows were returned."
        ),
        "Choose another range or review the configured source query.",
      );
      return;
    }
    const dateColumn = metric.date_column;
    const rows = source.slice().sort((left, right) => {
      const a = parseDate(left && left[dateColumn]);
      const b = parseDate(right && right[dateColumn]);
      return (a ? a.getTime() : 0) - (b ? b.getTime() : 0);
    });
    const seriesConfig = Array.isArray(metric.series) ? metric.series : [];
    const hasNumericValue = rows.some((row) => (
      seriesConfig.some((series) => finiteNumber(row && row[series.column]) !== null)
    ));
    if (!hasNumericValue) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || "No chartable values were returned.",
        "The rows do not contain numeric series values.",
      );
      return;
    }
    const chartStyle = chartStyleForMetric(state, metric);
    const presentation = chartPresentation(chartStyle);
    const isColumn = presentation.seriesType === "bar";
    const isArea = presentation.hasArea;
    const element = chartContainer(state, metric, chartStyle);
    if (!element) {
      return;
    }
    const theme = chartTheme(state);
    const dates = rows.map((row) => row && row[dateColumn]);
    const option = {
      ...baseChartOption(theme),
      color: seriesConfig.map((series, index) => colorForSeries(theme, series.color, index)),
      grid: {
        top: seriesConfig.length > 1 ? 48 : 20,
        right: 18,
        bottom: 42,
        left: 70,
        containLabel: false,
      },
      legend: seriesConfig.length > 1 ? {
        top: 2,
        left: 4,
        icon: "roundRect",
        itemWidth: 16,
        itemHeight: 3,
        textStyle: { color: theme.muted, fontSize: 11 },
      } : undefined,
      tooltip: {
        ...baseChartOption(theme).tooltip,
        trigger: "axis",
        axisPointer: isColumn
          ? stableBarInteraction(theme.green, 0).axisPointer
          : { type: "line", lineStyle: { color: theme.grid } },
        formatter(params) {
          const points = Array.isArray(params) ? params : [params];
          const title = points.length ? longDate(points[0].axisValue) : "";
          const rowsHtml = points.map((point) => (
            `<div style="display:flex;gap:18px;justify-content:space-between;margin-top:5px">`
              + `<span>${point.marker || ""}${escapeHtml(point.seriesName)}</span>`
              + `<strong>${escapeHtml(formatTooltipValue(
                point.value,
                metric.format,
                metric,
              ))}</strong>`
              + "</div>"
          )).join("");
          return `<strong>${escapeHtml(title)}</strong>${rowsHtml}`;
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: presentation.boundaryGap,
        data: dates,
        axisLine: { lineStyle: { color: theme.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: theme.muted,
          hideOverlap: true,
          margin: 14,
          formatter: shortDate,
        },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.muted,
          formatter: (value) => formatAxisValue(value, metric),
        },
        splitLine: { lineStyle: { color: theme.grid, type: "dashed" } },
      },
      series: seriesConfig.map((series, index) => {
        const seriesColor = colorForSeries(theme, series.color, index);
        const barInteraction = stableBarInteraction(
          seriesColor,
          [3, 3, 0, 0],
        );
        return {
          name: series.label,
          type: presentation.seriesType,
          data: rows.map((row) => {
            const value = finiteNumber(row && row[series.column]);
            return value === null ? null : value;
          }),
          smooth: isColumn ? false : 0.2,
          showSymbol: isColumn ? undefined : false,
          connectNulls: false,
          lineStyle: isColumn ? undefined : { width: 2.2 },
          barMaxWidth: isColumn ? 22 : undefined,
          itemStyle: isColumn ? barInteraction.itemStyle : undefined,
          areaStyle: isArea ? {
            opacity: seriesConfig.length === 1 ? 0.16 : 0.1,
            color: seriesColor,
          } : undefined,
          emphasis: isColumn ? barInteraction.emphasis : { focus: "series" },
          blur: isColumn ? barInteraction.blur : undefined,
          select: isColumn ? barInteraction.select : undefined,
        };
      }),
    };
    mountEChart(state, metric, element, option);
  }

  function rankedRows(rows, valueColumn, limit) {
    return (Array.isArray(rows) ? rows : [])
      .filter((row) => momentumNumber(row && row[valueColumn]) !== null)
      .slice()
      .sort((left, right) => (
        compareValues(right[valueColumn], left[valueColumn])
      ))
      .slice(0, limit || rows.length);
  }

  function renderBarChart(state, metric) {
    if (metric.growth_chart) {
      renderGrowthChart(state, metric);
      return;
    }
    const source = rowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    const limit = state.topN.get(metric.id)
      || Number(metric.default_top_n)
      || source.length;
    const valueColumn = metric.intelligence_value_column || metric.value_column;
    const categoryColumn = metric.intelligence_category_column || metric.category_column;
    const rows = rankedRows(source, valueColumn, limit);
    if (!rows.length) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || "No ranking rows were returned.",
        "Choose another range or review the configured source query.",
      );
      return;
    }
    const element = chartContainer(state, metric, "bar");
    if (!element) {
      return;
    }
    const theme = chartTheme(state);
    const horizontal = metric.orientation === "horizontal";
    if (horizontal) {
      element.style.height = `${Math.max(330, (rows.length * 24) + 88)}px`;
    }
    const categories = rows.map((row) => String(row[categoryColumn] || EMPTY_VALUE));
    const values = rows.map((row) => momentumNumber(row[valueColumn]) || 0);
    const barInteraction = stableBarInteraction(
      theme.green,
      horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
    );
    const categoryFormatter = (value) => (
      metric.shorten_categories ? shortAddress(value) : value
    );
    const categoryAxis = {
      type: "category",
      data: categories,
      inverse: horizontal,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.muted,
        interval: 0,
        hideOverlap: false,
        formatter: categoryFormatter,
        rotate: horizontal ? 0 : (categories.some((value) => value.length > 12) ? 22 : 0),
        width: horizontal ? 112 : undefined,
        overflow: horizontal ? "truncate" : undefined,
      },
    };
    const valueAxis = {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.muted,
        formatter: (value) => formatAxisValue(value, metric),
      },
      splitLine: { lineStyle: { color: theme.grid, type: "dashed" } },
    };
    const option = {
      ...baseChartOption(theme),
      grid: {
        top: 18,
        right: horizontal ? 74 : 18,
        bottom: horizontal ? 34 : 70,
        left: horizontal ? 128 : 64,
      },
      tooltip: {
        ...baseChartOption(theme).tooltip,
        trigger: "axis",
        axisPointer: barInteraction.axisPointer,
        formatter(params) {
          const point = Array.isArray(params) ? params[0] : params;
          const rowIndex = point && point.dataIndex;
          const fullCategory = categories[rowIndex] || "";
          const displayCategory = metric.shorten_categories
            ? shortAddress(fullCategory)
            : fullCategory;
          return `<strong title="${escapeHtml(fullCategory)}" aria-label="${escapeHtml(fullCategory)}">`
            + `${escapeHtml(displayCategory)}</strong>`
            + `<div style="margin-top:5px">${escapeHtml(formatTooltipValue(
              values[rowIndex],
              metric.format,
              metric,
            ))}</div>`;
        },
      },
      xAxis: horizontal ? valueAxis : categoryAxis,
      yAxis: horizontal ? categoryAxis : valueAxis,
      series: [{
        type: "bar",
        data: values,
        barMaxWidth: horizontal ? 18 : 42,
        itemStyle: barInteraction.itemStyle,
        label: horizontal ? {
          show: true,
          position: "right",
          color: theme.muted,
          formatter: (params) => formatAxisValue(params.value, metric),
        } : { show: false },
        emphasis: barInteraction.emphasis,
        blur: barInteraction.blur,
        select: barInteraction.select,
      }],
    };
    mountEChart(state, metric, element, option);
    if (metric.intelligence_component === "top_referred_depositors") {
      const chart = state.charts.get(metric.id);
      if (chart && typeof chart.on === "function") {
        chart.on("click", (event) => {
          const address = categories[Number(event && event.dataIndex)];
          if (address) {
            selectIntelligenceWallet(state, address, { scroll: true, updateUrl: true });
          }
        });
      }
    }
    if (metric.shorten_categories && element.isConnected) {
      appendChartAddressCopyControl(state, metric, categories);
    }
  }

  function appendChartAddressCopyControl(state, metric, categories) {
    const body = state.page.querySelector(`[data-metric-render="${metric.id}"]`);
    if (!body) {
      return;
    }
    const identifiers = [...new Set(categories.filter((value) => !isNil(value)))];
    if (!identifiers.length) {
      return;
    }
    const scope = body.ownerDocument;
    const control = createElement(
      scope,
      "div",
      "studio-chart-address-control studio-chart-address-controls",
    );
    const label = createElement(scope, "label", "studio-chart-address-select");
    label.appendChild(createElement(scope, "span", "", "Full address"));
    const select = createElement(scope, "select");
    select.dataset.chartAddressSelect = metric.id;
    select.setAttribute("aria-label", `Choose a full address from ${metric.name}`);
    identifiers.forEach((identifier) => {
      const option = createElement(scope, "option", "", shortAddress(identifier));
      option.value = identifier;
      option.title = identifier;
      option.setAttribute("aria-label", identifier);
      select.appendChild(option);
    });
    label.appendChild(select);
    const button = createElement(scope, "button", "studio-chart-address-copy", "Copy address");
    button.type = "button";
    button.dataset.chartAddressCopy = metric.id;
    const feedback = createElement(scope, "span", "studio-chart-address-feedback");
    feedback.setAttribute("aria-live", "polite");
    const explorer = createElement(scope, "a", "studio-chart-address-explorer", "Explorer ↗");
    explorer.target = "_blank";
    explorer.rel = "noopener noreferrer";
    const investigate = metric.intelligence_component === "top_referred_depositors"
      ? createElement(scope, "button", "studio-chart-address-investigate", "Investigate")
      : null;
    if (investigate) {
      investigate.type = "button";
    }

    function updateCopyTarget() {
      button.dataset.copyValue = select.value;
      button.title = select.value;
      button.setAttribute("aria-label", `Copy full address ${select.value}`);
      const details = explorerDetails(metric.default_chain || "ethereum");
      const url = explorerUrl(select.value, "address", metric.default_chain || "ethereum");
      explorer.hidden = !url;
      explorer.href = url || "#";
      explorer.title = details ? `Open address on ${details.label}` : "";
      explorer.setAttribute(
        "aria-label",
        details ? `Open full address ${select.value} on ${details.label}` : "Explorer unavailable",
      );
      if (investigate) {
        investigate.dataset.investigateWallet = select.value;
        investigate.setAttribute("aria-label", `Investigate wallet ${select.value}`);
      }
    }

    select.addEventListener("change", () => {
      updateCopyTarget();
      if (metric.intelligence_component === "top_referred_depositors") {
        selectIntelligenceWallet(state, select.value, { scroll: false, updateUrl: true });
      }
    });
    button.addEventListener("click", () => {
      copyText(button.dataset.copyValue, scope).then((copied) => {
        feedback.textContent = copied ? "Full address copied." : "Copy failed.";
        button.classList.toggle("is-copied", copied);
        root.setTimeout(() => {
          if (feedback.isConnected) {
            feedback.textContent = "";
            button.classList.remove("is-copied");
          }
        }, 1600);
      });
    });
    if (investigate) {
      investigate.addEventListener("click", () => {
        selectIntelligenceWallet(state, select.value, { scroll: true, updateUrl: true });
      });
    }
    updateCopyTarget();
    control.append(label, button, explorer);
    if (investigate) {
      control.appendChild(investigate);
    }
    control.appendChild(feedback);
    body.appendChild(control);
  }

  function sankeyStageColumns(metric) {
    const configured = metric && Array.isArray(metric.stage_columns)
      ? metric.stage_columns.filter((column) => (
        typeof column === "string" && column.trim()
      ))
      : [];
    if (configured.length === 2 || configured.length === 3) {
      return configured;
    }
    return metric && metric.source_column && metric.target_column
      ? [metric.source_column, metric.target_column]
      : [];
  }

  function sankeyNodeId(stageIndex, label) {
    return `stage-${stageIndex}:${String(label)}`;
  }

  function sankeyNumber(value) {
    if (typeof value === "number") {
      return Number.isFinite(value) ? value : null;
    }
    if (typeof value !== "string" || !value.trim()) {
      return null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function sankeyRowValue(row, metric, lastStageColumn) {
    const destinationStatus = String(
      row && row.destination_status || "",
    ).toLocaleLowerCase("en");
    const destinationLabel = String(row && row[lastStageColumn] || "")
      .toLocaleLowerCase("en");
    const isExited = destinationStatus === "exited" || destinationLabel === "exited";
    const valueColumn = isExited && metric.exit_value_column
      ? metric.exit_value_column
      : metric.value_column;
    return sankeyNumber(row && row[valueColumn]);
  }

  function sankeyDestinationGrouping(rows, metric, stages) {
    const topN = Number(metric && metric.destination_top_n);
    if (!Number.isInteger(topN) || topN < 1 || !stages.length) {
      return null;
    }
    const lastStageColumn = stages[stages.length - 1];
    const othersLabel = String(
      metric.destination_others_label || "Others",
    ).trim() || "Others";
    const preserved = new Set(
      (Array.isArray(metric.preserve_destinations) ? metric.preserve_destinations : [])
        .filter((label) => !isNil(label))
        .map((label) => String(label).toLocaleLowerCase("en")),
    );
    preserved.add("exited");
    const totals = new Map();
    (Array.isArray(rows) ? rows : []).forEach((row) => {
      const labelValue = row && row[lastStageColumn];
      const value = sankeyRowValue(row, metric, lastStageColumn);
      if (isNil(labelValue) || value === null || value <= 0) {
        return;
      }
      const label = String(labelValue);
      const status = String(row && row.destination_status || "")
        .toLocaleLowerCase("en");
      if (status === "exited" || preserved.has(label.toLocaleLowerCase("en"))) {
        return;
      }
      totals.set(label, (totals.get(label) || 0) + value);
    });
    const kept = new Set(
      [...totals.entries()]
        .sort((left, right) => (
          right[1] - left[1]
          || left[0].localeCompare(right[0], "en")
        ))
        .slice(0, topN)
        .map(([label]) => label),
    );
    const grouped = new Set(
      [...totals.keys()].filter((label) => !kept.has(label)),
    );
    return { grouped, othersLabel, preserved };
  }

  function aggregateSankeyRows(rows, metric) {
    const stages = sankeyStageColumns(metric);
    if (stages.length < 2) {
      return [];
    }
    const links = new Map();
    const destinationGrouping = sankeyDestinationGrouping(rows, metric, stages);
    (Array.isArray(rows) ? rows : []).forEach((row) => {
      const labels = stages.map((column) => row && row[column]);
      const value = sankeyRowValue(row, metric, stages[stages.length - 1]);
      if (labels.some(isNil) || value === null || value <= 0) {
        return;
      }
      const originalDestination = String(labels[labels.length - 1]);
      const groupedDestination = Boolean(
        destinationGrouping
        && destinationGrouping.grouped.has(originalDestination),
      );
      if (groupedDestination) {
        labels[labels.length - 1] = destinationGrouping.othersLabel;
      }
      for (let stageIndex = 0; stageIndex < labels.length - 1; stageIndex += 1) {
        const sourceLabel = String(labels[stageIndex]);
        const targetLabel = String(labels[stageIndex + 1]);
        const source = sankeyNodeId(stageIndex, sourceLabel);
        const target = sankeyNodeId(stageIndex + 1, targetLabel);
        const key = `${source}\u0000${target}`;
        const existing = links.get(key);
        if (existing) {
          existing.value += value;
          if (groupedDestination && stageIndex === labels.length - 2) {
            if (!(existing._groupedMembers instanceof Set)) {
              existing._groupedMembers = new Set();
            }
            existing._groupedMembers.add(originalDestination);
          }
        } else {
          const link = {
            source,
            target,
            sourceLabel,
            targetLabel,
            sourceStage: stageIndex,
            targetStage: stageIndex + 1,
            value,
          };
          if (groupedDestination && stageIndex === labels.length - 2) {
            link._groupedMembers = new Set([originalDestination]);
          }
          links.set(key, link);
        }
      }
    });
    return [...links.values()]
      .filter((link) => link.value > 0)
      .map((link) => {
        if (!(link._groupedMembers instanceof Set)) {
          return link;
        }
        const groupedMembers = [...link._groupedMembers]
          .sort((left, right) => left.localeCompare(right, "en"));
        const normalized = { ...link, groupedMembers };
        delete normalized._groupedMembers;
        return normalized;
      });
  }

  function sankeyConservation(links) {
    const incoming = new Map();
    const outgoing = new Map();
    let maximum = 0;
    (Array.isArray(links) ? links : []).forEach((link) => {
      const value = sankeyNumber(link && link.value);
      if (value === null || value <= 0) {
        return;
      }
      maximum = Math.max(maximum, value);
      incoming.set(link.target, (incoming.get(link.target) || 0) + value);
      outgoing.set(link.source, (outgoing.get(link.source) || 0) + value);
    });
    const tolerance = Math.max(1, maximum) * 1e-9;
    const deltas = [];
    incoming.forEach((input, node) => {
      if (!outgoing.has(node)) {
        return;
      }
      const output = outgoing.get(node);
      const delta = input - output;
      if (Math.abs(delta) > tolerance) {
        deltas.push({ node, incoming: input, outgoing: output, delta });
      }
    });
    return {
      valid: deltas.length === 0,
      tolerance,
      deltas,
    };
  }

  function isMobileFlow(state) {
    if (state.mobileQuery) {
      return state.mobileQuery.matches;
    }
    return Boolean(
      root && root.innerWidth && root.innerWidth <= STUDIO_MOBILE_BREAKPOINT,
    );
  }

  function renderSankeyList(state, metric, links) {
    const body = clearMetricBody(state, metric.id);
    if (!body) {
      return;
    }
    body.dataset.state = "ready";
    const wrapper = createElement(body.ownerDocument, "div", "studio-flow-list");
    const list = createElement(body.ownerDocument, "ol");
    const max = Math.max(...links.map((link) => link.value));
    links.slice().sort((a, b) => b.value - a.value).forEach((link) => {
      const item = createElement(body.ownerDocument, "li");
      const route = createElement(body.ownerDocument, "div", "studio-flow-route");
      route.append(
        createElement(body.ownerDocument, "span", "", link.sourceLabel),
        createElement(body.ownerDocument, "span", "", "→"),
        createElement(body.ownerDocument, "span", "", link.targetLabel),
      );
      route.children[1].setAttribute("aria-hidden", "true");
      item.append(
        route,
        createElement(
          body.ownerDocument,
          "strong",
          "",
          formatValue(link.value, metric.format, metric),
        ),
      );
      if (Array.isArray(link.groupedMembers) && link.groupedMembers.length) {
        item.appendChild(createElement(
          body.ownerDocument,
          "p",
          "studio-flow-members",
          `Grouped destinations: ${link.groupedMembers.join(", ")}`,
        ));
      }
      const bar = createElement(body.ownerDocument, "div", "studio-flow-bar");
      const fill = createElement(body.ownerDocument, "span");
      fill.style.width = `${Math.max(3, (link.value / max) * 100).toFixed(2)}%`;
      bar.appendChild(fill);
      item.appendChild(bar);
      list.appendChild(item);
    });
    wrapper.appendChild(list);
    body.appendChild(wrapper);
  }

  function renderSankey(state, metric) {
    const source = rowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    const links = aggregateSankeyRows(source, metric);
    if (!links.length) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || "No flow rows were returned.",
        "The Sankey requires positive source-to-target values.",
      );
      return;
    }
    const conservation = sankeyConservation(links);
    if (!conservation.valid) {
      renderMetricState(
        state,
        metric,
        "error",
        "The flow does not reconcile.",
        "Intermediate Sankey inflows and outflows must match before rendering.",
      );
      return;
    }
    if (isMobileFlow(state)) {
      renderSankeyList(state, metric, links);
      return;
    }
    const element = chartContainer(state, metric, "sankey");
    if (!element) {
      return;
    }
    const theme = chartTheme(state);
    const nodes = new Map();
    links.forEach((link) => {
      const existingSource = nodes.get(link.source) || {};
      nodes.set(link.source, {
        name: link.source,
        label: link.sourceLabel,
        stage: link.sourceStage,
        incoming: existingSource.incoming || 0,
        outgoing: (existingSource.outgoing || 0) + link.value,
      });
      const existingTarget = nodes.get(link.target) || {};
      nodes.set(link.target, {
        name: link.target,
        label: link.targetLabel,
        stage: link.targetStage,
        incoming: (existingTarget.incoming || 0) + link.value,
        outgoing: existingTarget.outgoing || 0,
      });
    });
    const compactLayout = metric.size === "medium";
    const option = {
      ...baseChartOption(theme),
      tooltip: {
        ...baseChartOption(theme).tooltip,
        trigger: "item",
        formatter(params) {
          if (params.dataType === "edge") {
            const groupedMembers = Array.isArray(params.data.groupedMembers)
              && params.data.groupedMembers.length
              ? `<div style="margin-top:5px;max-width:320px;white-space:normal">Grouped destinations: ${escapeHtml(params.data.groupedMembers.join(", "))}</div>`
              : "";
            return `<strong>${escapeHtml(params.data.sourceLabel)} → ${escapeHtml(params.data.targetLabel)}</strong>`
              + `<div style="margin-top:5px">${escapeHtml(formatTooltipValue(
                params.data.value,
                metric.format,
                metric,
              ))}</div>`
              + groupedMembers;
          }
          return `<strong>${escapeHtml(params.data.label || params.name)}</strong>`;
        },
      },
      series: [{
        type: "sankey",
        left: compactLayout ? 12 : 18,
        right: compactLayout ? 94 : 124,
        top: compactLayout ? 12 : 18,
        bottom: compactLayout ? 12 : 18,
        nodeAlign: "justify",
        nodeWidth: compactLayout ? 10 : 12,
        nodeGap: compactLayout ? 10 : 14,
        draggable: false,
        layoutIterations: 32,
        emphasis: { focus: "adjacency" },
        data: [...nodes.values()].map((node, index) => ({
          ...node,
          value: Math.max(node.incoming, node.outgoing),
          itemStyle: {
            color: [theme.green, theme.blue, theme.coral, theme.amber][index % 4],
            borderColor: theme.surface,
            borderWidth: 1,
          },
        })),
        links,
        label: {
          color: theme.ink,
          fontSize: compactLayout ? 10 : 11,
          width: compactLayout ? 82 : 108,
          overflow: "truncate",
          formatter(params) {
            return params.data.label || params.name;
          },
        },
        lineStyle: {
          color: "gradient",
          curveness: 0.52,
          opacity: 0.38,
        },
      }],
    };
    mountEChart(state, metric, element, option);
  }

  function tableCellValue(value, format, metric) {
    if (isNil(value)) {
      return EMPTY_VALUE;
    }
    return formatCompactDisplayValue(value, format || "", metric);
  }

  function fullTableCellValue(value, format, metric) {
    if (format === "currency_compact") {
      return formatValue(value, "currency", metric);
    }
    if (format === "integer_compact") {
      return formatValue(value, "integer", metric);
    }
    if (format === "percent" || format === "percentage_points") {
      return formatValue(value, format, metric);
    }
    return tableCellValue(value, format, metric);
  }

  function copyText(value, scope) {
    if (
      root &&
      root.navigator &&
      root.navigator.clipboard &&
      typeof root.navigator.clipboard.writeText === "function" &&
      root.isSecureContext
    ) {
      return root.navigator.clipboard.writeText(String(value))
        .then(() => true)
        .catch(() => copyTextFallback(value, scope));
    }
    return copyTextFallback(value, scope);
  }

  function copyTextFallback(value, scope) {
    if (!scope || !scope.body || typeof scope.execCommand !== "function") {
      return Promise.resolve(false);
    }
    const textarea = scope.createElement("textarea");
    textarea.value = String(value);
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.inset = "-9999px auto auto -9999px";
    scope.body.appendChild(textarea);
    textarea.select();
    let copied = false;
    try {
      copied = Boolean(scope.execCommand("copy"));
    } finally {
      textarea.remove();
    }
    return Promise.resolve(copied);
  }

  function tableStateFor(state, metric) {
    if (!state.tables.has(metric.id)) {
      const intelligenceDefaults = {
        top_depositors: "total_referral_deposits_usd",
        recent_referral_deposits: metric.date_column || "block_time",
        recent_etherfi_activity: metric.date_column || "block_time",
      };
      state.tables.set(metric.id, {
        page: 0,
        pageSize: Math.max(1, Number(metric.page_size) || 10),
        query: "",
        sortColumn: String(
          metric.default_sort_column
          || intelligenceDefaults[metric.intelligence_component]
          || "",
        ),
        sortDirection: String(metric.default_sort_direction || (
          metric.intelligence_component ? "descending" : "ascending"
        )) === "descending" ? "descending" : "ascending",
      });
    }
    const tableState = state.tables.get(metric.id);
    if (!Number.isInteger(Number(tableState.pageSize)) || Number(tableState.pageSize) < 1) {
      tableState.pageSize = Math.max(1, Number(metric.page_size) || 10);
    }
    if (!["ascending", "descending"].includes(tableState.sortDirection)) {
      tableState.sortDirection = "ascending";
    }
    return tableState;
  }

  function isRecentActivityTable(metric) {
    return Boolean(metric && [
      "recent_referral_deposits",
      "recent_etherfi_activity",
    ].includes(metric.intelligence_component));
  }

  function recentActivityTimeColumn(metric) {
    return String(metric && metric.date_column || "block_time");
  }

  function tableColumnLabel(metric, column, columnLabels) {
    if (isRecentActivityTable(metric)) {
      if (column === recentActivityTimeColumn(metric)) {
        return "Age";
      }
      if (column === "tx_hash") {
        return "Tx Hash";
      }
    }
    return columnLabels[column] || column.replace(/_/g, " ");
  }

  function addressCopyLabel(value, column) {
    const sourceColumn = String(column);
    const identifier = sourceColumn === "tx_hash"
      ? "transaction hash"
      : sourceColumn.replace(/_/g, " ");
    return `Copy ${identifier} ${String(value)}`;
  }

  function identifierKindForColumn(metric, column) {
    if ((metric.transaction_columns || []).includes(column)) {
      return "transaction";
    }
    if ((metric.address_columns || []).includes(column)) {
      return "address";
    }
    return "";
  }

  function chainForRow(metric, row) {
    if (metric.chain_column && row && !isNil(row[metric.chain_column])) {
      return row[metric.chain_column];
    }
    return metric.default_chain || "";
  }

  function appendCopyIcon(scope, button) {
    const svg = scope.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("studio-copy-icon-svg");
    svg.setAttribute("viewBox", "0 0 20 20");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("fill", "none");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    [
      ["3", "3"],
      ["7", "7"],
    ].forEach(([x, y]) => {
      const rectangle = scope.createElementNS("http://www.w3.org/2000/svg", "rect");
      rectangle.setAttribute("x", x);
      rectangle.setAttribute("y", y);
      rectangle.setAttribute("width", "10");
      rectangle.setAttribute("height", "10");
      rectangle.setAttribute("rx", "1.5");
      rectangle.setAttribute("stroke", "currentColor");
      rectangle.setAttribute("stroke-width", "1.5");
      rectangle.setAttribute("vector-effect", "non-scaling-stroke");
      svg.appendChild(rectangle);
    });
    const status = createElement(
      scope,
      "span",
      "visually-hidden studio-copy-status",
    );
    status.dataset.copyStatus = "";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    button.append(svg, status);
  }

  function appendRelativeAgeCell(scope, cell, value) {
    const time = createElement(scope, "time", "studio-relative-age");
    time.dataset.relativeTimestamp = String(value);
    time.tabIndex = 0;
    updateRelativeAgeElement(time);
    cell.appendChild(time);
  }

  function appendIdentifierCell(scope, cell, value, column, kind, chain, options) {
    const config = options || {};
    const wrapper = createElement(
      scope,
      "span",
      "studio-address-cell studio-identifier-actions",
    );
    const code = createElement(scope, "code", "", shortAddress(value));
    code.title = String(value);
    code.setAttribute("aria-label", String(value));
    const url = explorerUrl(value, kind, chain);
    if (url) {
      const details = explorerDetails(chain);
      const link = createElement(scope, "a", "studio-identifier-link");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = `Open ${String(value)} on ${details ? details.label : "explorer"}`;
      link.setAttribute(
        "aria-label",
        `Open full ${kind === "transaction" ? "transaction hash" : "address"} `
          + `${value} on ${details ? details.label : "explorer"}`,
      );
      link.appendChild(code);
      wrapper.appendChild(link);
    } else {
      wrapper.appendChild(code);
    }
    const compactCopy = Boolean(config.compactCopy);
    const button = createElement(
      scope,
      "button",
      `studio-copy-address${compactCopy ? " studio-copy-icon" : ""}`,
      compactCopy ? undefined : "Copy",
    );
    button.type = "button";
    button.dataset.copyValue = String(value);
    button.dataset.identifierCopy = column;
    button.dataset.copyIdentifier = column;
    const copyLabel = addressCopyLabel(value, column);
    button.setAttribute("aria-label", copyLabel);
    button.title = copyLabel;
    if (compactCopy) {
      appendCopyIcon(scope, button);
    }
    wrapper.appendChild(button);
    cell.appendChild(wrapper);
  }

  function showCopyFeedback(button, copied) {
    const compact = button.classList.contains("studio-copy-icon");
    button.classList.toggle("is-copied", copied);
    if (compact) {
      const status = button.querySelector("[data-copy-status]");
      if (status) {
        status.textContent = copied ? "Copied." : "Copy failed.";
      }
      if (!button.dataset.copyDefaultTitle) {
        button.dataset.copyDefaultTitle = button.title;
      }
      button.title = copied ? "Copied" : "Copy failed";
    } else {
      if (!button.dataset.copyDefaultText) {
        button.dataset.copyDefaultText = button.textContent;
      }
      button.textContent = copied ? "Copied" : "Copy failed";
    }
    if (button.__studioCopyFeedbackTimer && root && root.clearTimeout) {
      root.clearTimeout(button.__studioCopyFeedbackTimer);
    }
    if (!root || typeof root.setTimeout !== "function") {
      return;
    }
    button.__studioCopyFeedbackTimer = root.setTimeout(() => {
      if (!button.isConnected) {
        return;
      }
      button.classList.remove("is-copied");
      if (compact) {
        const status = button.querySelector("[data-copy-status]");
        if (status) {
          status.textContent = "";
        }
        button.title = button.dataset.copyDefaultTitle || button.title;
      } else {
        button.textContent = button.dataset.copyDefaultText || "Copy";
      }
      button.__studioCopyFeedbackTimer = null;
    }, 1600);
  }

  function appendTableSearchToolbar(state, metric, shell, tableState, view) {
    const scope = shell.ownerDocument;
    const toolbar = createElement(scope, "div", "studio-table-toolbar");
    const searchGroup = createElement(scope, "div", "studio-table-search");
    const label = createElement(scope, "label", "visually-hidden", `Search ${metric.name}`);
    const inputId = `studio-table-search-${metric.id}`;
    label.htmlFor = inputId;
    const input = createElement(scope, "input");
    input.id = inputId;
    input.type = "search";
    input.placeholder = "Search this table";
    input.value = tableState.query;
    input.dataset.tableSearch = metric.id;
    input.setAttribute("aria-label", `Search ${metric.name}`);
    const clear = createElement(scope, "button", "studio-table-search-clear", "Clear");
    clear.type = "button";
    clear.dataset.tableSearchClear = metric.id;
    clear.disabled = !tableState.query;
    clear.setAttribute("aria-label", `Clear ${metric.name} search`);
    searchGroup.append(label, input, clear);
    toolbar.append(
      searchGroup,
      createElement(
        scope,
        "span",
        "studio-table-search-count",
        tableState.query
          ? `${view.filteredRows} of ${view.totalRows} matching`
          : `${view.totalRows} rows`,
      ),
    );
    input.addEventListener("input", () => {
      const cursor = input.selectionStart;
      tableState.query = input.value;
      tableState.page = 0;
      renderTable(state, metric, { focusSearch: true, cursor });
    });
    clear.addEventListener("click", () => {
      tableState.query = "";
      tableState.page = 0;
      renderTable(state, metric, { focusSearch: true, cursor: 0 });
    });
    shell.appendChild(toolbar);
  }

  function restoreTableSearchFocus(body, metric, renderOptions) {
    if (!renderOptions || !renderOptions.focusSearch) {
      return;
    }
    const input = body.querySelector(`[data-table-search="${metric.id}"]`);
    if (!input) {
      return;
    }
    input.focus();
    if (typeof input.setSelectionRange === "function") {
      const cursor = Math.max(0, Number(renderOptions.cursor) || 0);
      input.setSelectionRange(cursor, cursor);
    }
  }

  function renderTable(state, metric, renderOptions) {
    const source = rowsForMetric(state, metric);
    if (!Array.isArray(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    if (!source.length) {
      renderMetricState(
        state,
        metric,
        "empty",
        metric.empty_message || "No table rows were returned.",
        "Choose another range or review the configured source query.",
      );
      return;
    }
    const tableState = tableStateFor(state, metric);
    const configuredColumns = Array.isArray(metric.table_columns)
      ? metric.table_columns
      : metric.intelligence_component && Array.isArray(metric.intelligence_columns)
        ? metric.intelligence_columns
        : metric.columns;
    const columns = Array.isArray(configuredColumns)
      ? configuredColumns
      : inferredColumns(source);
    const columnFormats = metric.intelligence_component
      && metric.intelligence_column_formats
      ? metric.intelligence_column_formats
      : metric.column_formats || {};
    const columnLabels = metric.intelligence_component
      && metric.intelligence_column_labels
      ? metric.intelligence_column_labels
      : metric.column_labels || {};
    const view = deriveTableView(source, columns, {
      query: tableState.query,
      searchColumns: uniqueColumns([
        ...columns,
        ...(Array.isArray(metric.table_search_columns)
          ? metric.table_search_columns
          : []),
      ]),
      columnFormats,
      metric,
      sortColumn: tableState.sortColumn,
      sortDirection: tableState.sortDirection,
      page: tableState.page,
      pageSize: tableState.pageSize,
    });
    tableState.page = view.page;
    const body = clearMetricBody(state, metric.id);
    if (!body) {
      return;
    }
    body.dataset.state = "ready";
    const shell = createElement(body.ownerDocument, "div", "studio-table-shell");
    appendTableSearchToolbar(state, metric, shell, tableState, view);
    if (!view.filteredRows) {
      const noResults = createElement(
        body.ownerDocument,
        "div",
        "studio-table-no-results studio-metric-state studio-empty-state",
      );
      noResults.append(
        createElement(body.ownerDocument, "strong", "", "No rows match this search."),
        createElement(
          body.ownerDocument,
          "p",
          "",
          "Clear the search or try a different term.",
        ),
      );
      noResults.dataset.tableNoResults = metric.id;
      shell.appendChild(noResults);
      body.appendChild(shell);
      restoreTableSearchFocus(body, metric, renderOptions);
      return;
    }
    const scroll = createElement(body.ownerDocument, "div", "studio-table-scroll");
    const table = createElement(body.ownerDocument, "table", "studio-data-table");
    const head = body.ownerDocument.createElement("thead");
    const headerRow = body.ownerDocument.createElement("tr");
    columns.forEach((column) => {
      const cell = body.ownerDocument.createElement("th");
      cell.scope = "col";
      cell.dataset.tableColumn = column;
      const active = tableState.sortColumn === column;
      cell.setAttribute("aria-sort", active ? tableState.sortDirection : "none");
      const button = createElement(
        body.ownerDocument,
        "button",
        `studio-table-sort${active ? " is-active" : ""}`,
      );
      button.type = "button";
      button.dataset.tableSort = column;
      button.appendChild(createElement(
        body.ownerDocument,
        "span",
        "",
        tableColumnLabel(metric, column, columnLabels),
      ));
      button.appendChild(createElement(
        body.ownerDocument,
        "span",
        "studio-sort-indicator",
        active ? (tableState.sortDirection === "ascending" ? "↑" : "↓") : "↕",
      ));
      cell.appendChild(button);
      headerRow.appendChild(cell);
    });
    head.appendChild(headerRow);
    const tableBody = body.ownerDocument.createElement("tbody");
    view.rows.forEach((row) => {
      const tableRow = body.ownerDocument.createElement("tr");
      const investigateColumn = metric.investigate_address_column
        || (metric.intelligence_component && Array.isArray(metric.address_columns)
          ? metric.address_columns[0]
          : "");
      const investigateAddress = investigateColumn && row
        ? normalizeWalletAddress(row[investigateColumn])
        : "";
      if (investigateAddress) {
        tableRow.dataset.investigateWallet = investigateAddress;
        tableRow.tabIndex = 0;
        tableRow.setAttribute("aria-label", `Investigate wallet ${investigateAddress}`);
        tableRow.classList.toggle(
          "is-selected-wallet",
          investigateAddress === state.selectedWallet,
        );
      }
      columns.forEach((column) => {
        const cell = body.ownerDocument.createElement("td");
        cell.dataset.tableColumn = column;
        const value = row && row[column];
        const identifierKind = identifierKindForColumn(metric, column);
        if (
          isRecentActivityTable(metric)
          && column === recentActivityTimeColumn(metric)
          && !isNil(value)
        ) {
          appendRelativeAgeCell(body.ownerDocument, cell, value);
        } else if (identifierKind && !isNil(value)) {
          appendIdentifierCell(
            body.ownerDocument,
            cell,
            value,
            column,
            identifierKind,
            chainForRow(metric, row),
            { compactCopy: isRecentActivityTable(metric) },
          );
        } else if (isNil(value)) {
          cell.appendChild(createElement(
            body.ownerDocument,
            "span",
            "studio-null-value",
            EMPTY_VALUE,
          ));
        } else if (Array.isArray(value)) {
          const tagList = createElement(body.ownerDocument, "span", "studio-table-tag-list");
          const compactValues = value.map(String).filter(Boolean);
          compactValues.slice(0, 3).forEach((item) => {
            tagList.appendChild(createElement(
              body.ownerDocument,
              "span",
              "studio-table-tag",
              item,
            ));
          });
          if (compactValues.length > 3) {
            tagList.appendChild(createElement(
              body.ownerDocument,
              "span",
              "studio-table-tag studio-table-tag-more",
              `+${compactValues.length - 3}`,
            ));
          }
          tagList.title = compactValues.join(", ");
          tagList.setAttribute("aria-label", compactValues.join(", "));
          cell.appendChild(tagList);
        } else {
          const format = columnFormats[column];
          const displayValue = tableCellValue(value, format, metric);
          const compactActivityText = metric.intelligence_component === "recent_etherfi_activity"
            && ["event", "project", "label"].includes(column);
          if (compactActivityText) {
            const text = createElement(
              body.ownerDocument,
              "span",
              "studio-table-compact-text",
              displayValue,
            );
            text.title = String(value);
            text.setAttribute("aria-label", String(value));
            cell.appendChild(text);
          } else {
            cell.textContent = displayValue;
          }
          const signedColumns = Array.isArray(metric.signed_value_columns)
            ? metric.signed_value_columns
            : metric.intelligence_component === "recent_etherfi_activity"
              ? ["amount_usd"]
              : [];
          if (signedColumns.includes(column)) {
            const numeric = momentumNumber(value);
            cell.classList.toggle("studio-value-positive", numeric !== null && numeric > 0);
            cell.classList.toggle("studio-value-negative", numeric !== null && numeric < 0);
          }
          if ([
            "currency_compact",
            "integer_compact",
            "percent",
            "percentage_points",
          ].includes(format)) {
            const fullValue = fullTableCellValue(value, format, metric);
            cell.title = fullValue;
            cell.setAttribute("aria-label", fullValue);
          }
        }
        tableRow.appendChild(cell);
      });
      tableBody.appendChild(tableRow);
    });
    table.append(head, tableBody);
    scroll.appendChild(table);
    shell.appendChild(scroll);

    const pagination = createElement(body.ownerDocument, "nav", "studio-table-pagination");
    pagination.setAttribute("aria-label", `${metric.name} pagination`);
    pagination.appendChild(createElement(
      body.ownerDocument,
      "p",
      "",
      `Rows ${view.start + 1}–${view.end} of ${view.filteredRows}`
        + (view.filteredRows !== view.totalRows ? ` matching · ${view.totalRows} total` : ""),
    ));
    const controls = createElement(body.ownerDocument, "div");
    const pageSizeOptions = Array.isArray(metric.page_size_options)
      ? metric.page_size_options.map(Number).filter((value) => Number.isInteger(value) && value > 0)
      : metric.intelligence_component ? [10, 25, 50, 100] : [];
    if (pageSizeOptions.length) {
      const pageSizeLabel = createElement(
        body.ownerDocument,
        "label",
        "studio-table-page-size",
      );
      pageSizeLabel.appendChild(createElement(body.ownerDocument, "span", "", "Rows"));
      const pageSizeSelect = createElement(body.ownerDocument, "select");
      pageSizeSelect.dataset.tablePageSize = metric.id;
      pageSizeSelect.setAttribute("aria-label", `Rows per page for ${metric.name}`);
      Array.from(new Set([...pageSizeOptions, tableState.pageSize]))
        .sort((left, right) => left - right)
        .forEach((value) => {
          const option = createElement(body.ownerDocument, "option", "", value);
          option.value = String(value);
          option.selected = value === tableState.pageSize;
          pageSizeSelect.appendChild(option);
        });
      pageSizeLabel.appendChild(pageSizeSelect);
      controls.appendChild(pageSizeLabel);
    }
    const previous = createElement(body.ownerDocument, "button", "", "Previous");
    previous.type = "button";
    previous.dataset.tablePage = "prev";
    previous.disabled = tableState.page === 0;
    const pageLabel = createElement(
      body.ownerDocument,
      "span",
      "",
      `Page ${tableState.page + 1} of ${view.pageCount}`,
    );
    pageLabel.setAttribute("aria-live", "polite");
    const next = createElement(body.ownerDocument, "button", "", "Next");
    next.type = "button";
    next.dataset.tablePage = "next";
    next.disabled = tableState.page >= view.pageCount - 1;
    controls.append(previous, pageLabel, next);
    pagination.appendChild(controls);
    shell.appendChild(pagination);
    body.appendChild(shell);
    restoreTableSearchFocus(body, metric, renderOptions);

    shell.querySelectorAll("[data-table-sort]").forEach((button) => {
      button.addEventListener("click", () => {
        const column = button.dataset.tableSort;
        if (tableState.sortColumn === column) {
          tableState.sortDirection = tableState.sortDirection === "ascending"
            ? "descending"
            : "ascending";
        } else {
          tableState.sortColumn = column;
          tableState.sortDirection = "ascending";
        }
        tableState.page = 0;
        renderTable(state, metric);
      });
    });
    shell.querySelectorAll("[data-table-page]").forEach((button) => {
      button.addEventListener("click", () => {
        tableState.page += button.dataset.tablePage === "next" ? 1 : -1;
        renderTable(state, metric);
      });
    });
    shell.querySelectorAll("[data-table-page-size]").forEach((select) => {
      select.addEventListener("change", () => {
        const pageSize = Number(select.value);
        if (!Number.isInteger(pageSize) || pageSize < 1) {
          return;
        }
        tableState.pageSize = pageSize;
        tableState.page = 0;
        renderTable(state, metric);
      });
    });
    shell.querySelectorAll("[data-investigate-wallet]").forEach((row) => {
      const selectWallet = () => selectIntelligenceWallet(
        state,
        row.dataset.investigateWallet,
        { scroll: true, updateUrl: true },
      );
      row.addEventListener("click", (event) => {
        if (event.target && event.target.closest && event.target.closest("[data-copy-value]")) {
          return;
        }
        selectWallet();
      });
      row.addEventListener("keydown", (event) => {
        if (
          event.target
          && event.target !== row
          && event.target.closest
          && event.target.closest("a, button, input, select")
        ) {
          return;
        }
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          selectWallet();
        }
      });
    });
    shell.querySelectorAll("[data-copy-value]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        copyText(button.dataset.copyValue, body.ownerDocument).then((copied) => {
          showCopyFeedback(button, copied);
        });
      });
    });
  }

  function intelligenceSource(state, metric) {
    return sourceForMetric(
      state,
      metric,
      metric.derived_data_source || metric.data_source || INTELLIGENCE_SOURCE,
    );
  }

  function concentrationModel(source, measure) {
    const measureKey = measure === "attributed_tvl"
      ? "attributed_tvl"
      : "referral_deposits";
    const configured = source && source.concentration
      && source.concentration[measureKey];
    if (configured && typeof configured === "object") {
      const tiers = Array.isArray(configured.tiers) ? configured.tiers : [];
      const configuredRanking = Array.isArray(configured.ranked_addresses)
        ? configured.ranked_addresses
        : [];
      const valueColumn = measureKey === "attributed_tvl"
        ? "attributed_tvl_usd"
        : "total_referral_deposits_usd";
      const totalNumeric = momentumNumber(configured.total_usd) || 0;
      const ranking = configuredRanking.map((entry, index) => {
        const address = typeof entry === "string" ? entry : entry && entry.address;
        const wallet = intelligenceWalletForAddress(source, address);
        const valueUsd = entry && typeof entry === "object"
          ? entry.value_usd ?? entry[valueColumn]
          : wallet && wallet[valueColumn];
        return {
          ...(entry && typeof entry === "object" ? entry : {}),
          rank: entry && typeof entry === "object" && entry.rank || index + 1,
          address: wallet && wallet.address || address || "",
          value_usd: valueUsd ?? "",
          share: entry && typeof entry === "object" && entry.share !== undefined
            ? entry.share
            : totalNumeric > 0 ? (momentumNumber(valueUsd) || 0) / totalNumeric : 0,
        };
      });
      return {
        measure: measureKey,
        totalUsd: configured.total_usd,
        tiers: tiers.map((tier) => ({
          topN: Number(tier.top_n),
          valueUsd: tier.value_usd,
          share: tier.share,
        })).filter((tier) => Number.isInteger(tier.topN) && tier.topN > 0),
        ranking: ranking.slice(),
      };
    }
    const valueColumn = measureKey === "attributed_tvl"
      ? "attributed_tvl_usd"
      : "total_referral_deposits_usd";
    const ranking = intelligenceWallets(source)
      .map((wallet) => ({
        address: wallet.address,
        value_usd: wallet[valueColumn],
      }))
      .filter((row) => momentumNumber(row.value_usd) !== null)
      .sort((left, right) => compareValues(right.value_usd, left.value_usd));
    const totalUsd = ranking.reduce(
      (total, row) => total + (momentumNumber(row.value_usd) || 0),
      0,
    );
    return {
      measure: measureKey,
      totalUsd,
      tiers: [1, 5, 10, 25].map((topN) => {
        const valueUsd = ranking.slice(0, topN).reduce(
          (total, row) => total + (momentumNumber(row.value_usd) || 0),
          0,
        );
        return { topN, valueUsd, share: totalUsd > 0 ? valueUsd / totalUsd : 0 };
      }),
      ranking,
    };
  }

  function renderReferralConcentration(state, metric) {
    const source = intelligenceSource(state, metric);
    if (!isUsableSource(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    const defaultMeasure = metric.default_concentration_measure === "attributed_tvl"
      ? "attributed_tvl"
      : "referral_deposits";
    const measure = state.intelligenceMeasures.get(metric.id) || defaultMeasure;
    const model = concentrationModel(source, measure);
    const body = clearMetricBody(state, metric.id);
    if (!body) {
      return;
    }
    body.dataset.state = "ready";
    const scope = body.ownerDocument;
    const shell = createElement(scope, "div", "studio-concentration");
    const toggle = createElement(scope, "div", "studio-concentration-toggle");
    toggle.setAttribute("role", "group");
    toggle.setAttribute("aria-label", "Concentration measure");
    [
      ["referral_deposits", "Referral Deposits"],
      ["attributed_tvl", "Attributed TVL"],
    ].forEach(([value, label]) => {
      const button = createElement(scope, "button", "", label);
      button.type = "button";
      button.dataset.concentrationMeasure = value;
      const active = value === measure;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
      button.addEventListener("click", () => {
        state.intelligenceMeasures.set(metric.id, value);
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      });
      toggle.appendChild(button);
    });
    const topTen = model.tiers.find((tier) => tier.topN === 10)
      || model.tiers[model.tiers.length - 1]
      || { share: 0 };
    const topTenShare = momentumNumber(topTen.share) || 0;
    const headline = createElement(scope, "div", "studio-concentration-headline");
    headline.append(
      createElement(scope, "strong", "", formatValue(topTenShare, "percent", metric)),
      createElement(
        scope,
        "span",
        "",
        measure === "attributed_tvl"
          ? "held by the 10 largest attributed positions"
          : "from the 10 largest depositors",
      ),
    );
    const tierList = createElement(scope, "div", "studio-concentration-tiers");
    model.tiers.filter((tier) => [1, 5, 10, 25].includes(tier.topN)).forEach((tier) => {
      const share = momentumNumber(tier.share) || 0;
      const item = createElement(scope, "div", "studio-concentration-tier");
      const heading = createElement(scope, "div", "studio-concentration-tier-heading");
      heading.append(
        createElement(scope, "span", "", `Top ${tier.topN}`),
        createElement(scope, "strong", "", formatValue(share, "percent", metric)),
      );
      const track = createElement(scope, "div", "studio-concentration-track");
      track.setAttribute("role", "progressbar");
      track.setAttribute("aria-valuemin", "0");
      track.setAttribute("aria-valuemax", "100");
      track.setAttribute("aria-valuenow", String(Math.round(share * 100)));
      const fill = createElement(scope, "span", "studio-concentration-fill");
      fill.style.width = `${Math.max(0, Math.min(100, share * 100))}%`;
      track.appendChild(fill);
      item.append(heading, track);
      tierList.appendChild(item);
    });
    shell.append(
      toggle,
      headline,
      tierList,
      createElement(
        scope,
        "p",
        "studio-concentration-total",
        `${formatCompactDisplayValue(model.totalUsd || 0, "currency_compact", metric)} selected total`,
      ),
    );
    body.appendChild(shell);
  }

  function intelligenceWalletMetric(state) {
    return state.metrics.find((metric) => (
      metric.intelligence_component === "wallet_investigation"
    )) || null;
  }

  function persistWalletSelection(state) {
    persistDashboardValue(state.walletStorageKey, state.selectedWallet || "");
    updateStudioUrlParameter("wallet", state.selectedWallet || "");
  }

  function selectIntelligenceWallet(state, address, options) {
    const config = options || {};
    const normalized = normalizeWalletAddress(address);
    if (!normalized) {
      state.walletInputError = "Enter a valid 42-character EVM address.";
      const walletMetric = intelligenceWalletMetric(state);
      if (walletMetric) {
        state.dirty.add(walletMetric.id);
        renderMetric(state, walletMetric);
      }
      return false;
    }
    state.selectedWallet = normalized;
    state.walletInputError = "";
    state.recentWallets = [
      normalized,
      ...(state.recentWallets || []).filter((value) => value !== normalized),
    ].slice(0, 5);
    persistRecentWallets(state);
    if (config.updateUrl !== false) {
      persistWalletSelection(state);
    }
    state.metrics.filter((metric) => [
      "top_depositors",
      "recent_referral_deposits",
      "recent_etherfi_activity",
    ].includes(metric.intelligence_component)).forEach((metric) => {
      state.dirty.add(metric.id);
    });
    const walletMetric = intelligenceWalletMetric(state);
    if (walletMetric) {
      const card = state.page.querySelector(`[data-studio-metric-id="${walletMetric.id}"]`);
      if (card && card.hidden) {
        state.visible.add(walletMetric.id);
        applyVisibility(state, true);
      } else {
        state.dirty.add(walletMetric.id);
        renderMetric(state, walletMetric);
      }
      if (config.scroll && card) {
        const scroll = () => card.scrollIntoView({
          behavior: reducedMotionPreferred() ? "auto" : "smooth",
          block: "start",
        });
        if (root && typeof root.requestAnimationFrame === "function") {
          root.requestAnimationFrame(scroll);
        } else {
          scroll();
        }
      }
    }
    renderVisibleMetrics(state);
    return true;
  }

  function clearIntelligenceWallet(state) {
    state.selectedWallet = "";
    state.walletInputError = "";
    persistWalletSelection(state);
    const metric = intelligenceWalletMetric(state);
    if (metric) {
      state.dirty.add(metric.id);
      renderMetric(state, metric);
    }
  }

  function bindIntelligenceCopyButtons(container) {
    container.querySelectorAll("[data-copy-value]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        copyText(button.dataset.copyValue, container.ownerDocument).then((copied) => {
          showCopyFeedback(button, copied);
        });
      });
    });
  }

  function appendWalletDetailTable(scope, parent, settings) {
    const section = createElement(scope, "section", "studio-wallet-detail-section");
    section.appendChild(createElement(scope, "h4", "", settings.title));
    const rows = Array.isArray(settings.rows) ? settings.rows : [];
    if (!rows.length) {
      section.appendChild(createElement(
        scope,
        "p",
        "studio-wallet-empty",
        settings.emptyMessage || "No records are available for this wallet.",
      ));
      parent.appendChild(section);
      return;
    }
    const scroll = createElement(scope, "div", "studio-wallet-table-scroll");
    const table = createElement(scope, "table", "studio-data-table studio-wallet-table");
    const head = scope.createElement("thead");
    const headerRow = scope.createElement("tr");
    settings.columns.forEach((column) => {
      const cell = scope.createElement("th");
      cell.scope = "col";
      cell.dataset.tableColumn = column;
      cell.textContent = settings.labels[column] || column.replace(/_/g, " ");
      headerRow.appendChild(cell);
    });
    head.appendChild(headerRow);
    const body = scope.createElement("tbody");
    rows.forEach((row) => {
      const tableRow = scope.createElement("tr");
      settings.columns.forEach((column) => {
        const cell = scope.createElement("td");
        cell.dataset.tableColumn = column;
        const value = row && row[column];
        if (settings.relativeTimeColumns.includes(column) && !isNil(value)) {
          appendRelativeAgeCell(scope, cell, value);
        } else if (column === "tx_hash" && !isNil(value)) {
          appendIdentifierCell(
            scope,
            cell,
            value,
            column,
            "transaction",
            row.blockchain || row.chain || "ethereum",
          );
        } else if (isNil(value)) {
          cell.textContent = EMPTY_VALUE;
        } else {
          const format = settings.formats[column] || "";
          cell.textContent = formatCompactDisplayValue(
            value,
            format,
            settings.metric,
          );
          if (["currency_compact", "integer_compact", "percent"].includes(format)) {
            const full = fullTableCellValue(value, format, settings.metric);
            cell.title = full;
            cell.setAttribute("aria-label", full);
          }
          if (settings.signedColumns.includes(column)) {
            const numeric = momentumNumber(value);
            cell.classList.toggle("studio-value-positive", numeric !== null && numeric > 0);
            cell.classList.toggle("studio-value-negative", numeric !== null && numeric < 0);
          }
        }
        tableRow.appendChild(cell);
      });
      body.appendChild(tableRow);
    });
    table.append(head, body);
    scroll.appendChild(table);
    section.appendChild(scroll);
    parent.appendChild(section);
  }

  function appendWalletSummaryCards(scope, parent, wallet, metric) {
    const grid = createElement(scope, "dl", "studio-wallet-summary-grid");
    [
      ["Total Referral Deposits", wallet.total_referral_deposits_usd, "currency_compact"],
      ["Attributed TVL", wallet.attributed_tvl_usd, "currency_compact"],
      ["Depositor Type", wallet.depositor_type, "text"],
      ["Retention Rate", wallet.retention_rate, "percent"],
      ["Products Deposited", wallet.num_products_deposited, "integer"],
    ].forEach(([label, value, format]) => {
      const item = createElement(scope, "div", "studio-wallet-summary-item");
      item.append(
        createElement(scope, "dt", "", label),
        createElement(
          scope,
          "dd",
          "",
          format === "text"
            ? (isNil(value) ? EMPTY_VALUE : String(value))
            : formatCompactDisplayValue(isNil(value) ? 0 : value, format, metric),
        ),
      );
      grid.appendChild(item);
    });
    parent.appendChild(grid);
  }

  function renderWalletInvestigation(state, metric) {
    const source = intelligenceSource(state, metric);
    if (!isUsableSource(source)) {
      const problem = sourceProblem(source);
      renderMetricState(state, metric, "error", problem.title, problem.message);
      return;
    }
    const body = clearMetricBody(state, metric.id);
    if (!body) {
      return;
    }
    body.dataset.state = "ready";
    const scope = body.ownerDocument;
    const shell = createElement(scope, "div", "studio-wallet-investigation");
    const form = createElement(scope, "form", "studio-wallet-search");
    form.noValidate = true;
    const label = createElement(scope, "label", "visually-hidden", "Wallet address");
    const input = createElement(scope, "input");
    input.type = "search";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = "Paste a full 0x wallet address";
    input.value = state.selectedWallet || "";
    input.setAttribute("aria-label", "Wallet address");
    input.setAttribute("aria-describedby", `${metric.id}-wallet-feedback`);
    const submit = createElement(scope, "button", "", "Inspect wallet");
    submit.type = "submit";
    const clear = createElement(scope, "button", "studio-wallet-clear", "Clear");
    clear.type = "button";
    clear.disabled = !state.selectedWallet;
    form.append(label, input, submit, clear);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      selectIntelligenceWallet(state, input.value, { scroll: false, updateUrl: true });
    });
    clear.addEventListener("click", () => clearIntelligenceWallet(state));
    shell.appendChild(form);
    const feedback = createElement(
      scope,
      "p",
      `studio-wallet-feedback${state.walletInputError ? " is-error" : ""}`,
      state.walletInputError || "Select a chart bar or table row, or enter an address.",
    );
    feedback.id = `${metric.id}-wallet-feedback`;
    feedback.setAttribute("aria-live", "polite");
    shell.appendChild(feedback);
    if ((state.recentWallets || []).length) {
      const recent = createElement(scope, "div", "studio-wallet-recents");
      recent.appendChild(createElement(scope, "span", "", "Recent"));
      state.recentWallets.forEach((address) => {
        const button = createElement(scope, "button", "", shortAddress(address));
        button.type = "button";
        button.title = address;
        button.setAttribute("aria-label", `Inspect recent wallet ${address}`);
        button.addEventListener("click", () => selectIntelligenceWallet(
          state,
          address,
          { scroll: false, updateUrl: true },
        ));
        recent.appendChild(button);
      });
      shell.appendChild(recent);
    }
    if (!state.selectedWallet) {
      const empty = createElement(scope, "div", "studio-wallet-intro");
      empty.append(
        createElement(scope, "strong", "", "Choose a referred wallet to investigate."),
        createElement(scope, "p", "", "Deposits, retained positions, and later ether.fi activity stay local to this snapshot."),
      );
      shell.appendChild(empty);
      body.appendChild(shell);
      return;
    }
    const wallet = intelligenceWalletForAddress(source, state.selectedWallet);
    if (!wallet) {
      const empty = createElement(scope, "div", "studio-wallet-intro studio-wallet-not-found");
      empty.append(
        createElement(scope, "strong", "", "No referred-wallet data was found."),
        createElement(scope, "p", "", "The address is valid but is not present in the active Studio snapshot."),
      );
      shell.appendChild(empty);
      body.appendChild(shell);
      return;
    }
    const selectedHeader = createElement(scope, "header", "studio-wallet-selected-header");
    const identity = createElement(scope, "div", "studio-wallet-identity");
    identity.append(
      createElement(scope, "span", "studio-wallet-kicker", "Selected wallet"),
      createElement(scope, "strong", "studio-wallet-address", shortAddress(wallet.address)),
    );
    const identityActions = createElement(scope, "div", "studio-wallet-identity-actions");
    const copy = createElement(scope, "button", "", "Copy address");
    copy.type = "button";
    copy.dataset.copyValue = wallet.address;
    copy.setAttribute("aria-label", `Copy full address ${wallet.address}`);
    identityActions.appendChild(copy);
    const walletExplorer = explorerUrl(wallet.address, "address", "ethereum");
    if (walletExplorer) {
      const link = createElement(scope, "a", "", "Explorer ↗");
      link.href = walletExplorer;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `Open full address ${wallet.address} on Etherscan`);
      identityActions.appendChild(link);
    }
    selectedHeader.append(identity, identityActions);
    shell.appendChild(selectedHeader);
    appendWalletSummaryCards(scope, shell, wallet, metric);

    const positions = intelligenceWalletCollection(wallet, ["positions"])
      .map((row) => {
        const exited = String(row.destination_status || "").toLocaleLowerCase("en") === "exited"
          || String(row.current_token || "").toLocaleLowerCase("en") === "exited";
        return {
          ...row,
          exited_balance: exited
            ? (row.exited_balance ?? row.attributed_balance)
            : "",
        };
      });
    const deposits = filterRowsByRange(
      intelligenceWalletCollection(wallet, ["referral_deposits", "deposits"]),
      "block_time",
      state.activeRange,
      state.referenceDate,
    ).sort((left, right) => compareValues(right.block_time, left.block_time));
    const activity = filterRowsByRange(
      intelligenceWalletCollection(wallet, ["activity", "activities"]),
      "block_time",
      state.activeRange,
      state.referenceDate,
    ).sort((left, right) => compareValues(right.block_time, left.block_time));
    appendWalletDetailTable(scope, shell, {
      title: "Current attributed positions",
      rows: positions,
      columns: ["strategy_symbol", "current_token", "current_token_category", "referral_balance", "current_balance", "attributed_balance", "exited_balance"],
      labels: { strategy_symbol: "Deposited Product", current_token: "Current Token", current_token_category: "Category", referral_balance: "Referral Balance", current_balance: "Current Balance", attributed_balance: "Attributed Balance", exited_balance: "Exited Balance" },
      formats: { referral_balance: "currency_compact", current_balance: "currency_compact", attributed_balance: "currency_compact", exited_balance: "currency_compact" },
      signedColumns: [],
      relativeTimeColumns: [],
      metric,
      emptyMessage: "No current attributed positions are available for this wallet.",
    });
    appendWalletDetailTable(scope, shell, {
      title: "Referral deposit history",
      rows: deposits,
      columns: ["block_time", "strategy_symbol", "amount_usd", "blockchain", "tx_hash"],
      labels: { block_time: "Age", strategy_symbol: "Product", amount_usd: "Amount", blockchain: "Chain", tx_hash: "Transaction" },
      formats: { amount_usd: "currency_compact" },
      signedColumns: [],
      relativeTimeColumns: ["block_time"],
      metric,
      emptyMessage: "No referral deposits are available for this wallet in the selected period.",
    });
    appendWalletDetailTable(scope, shell, {
      title: "Later ether.fi activity",
      rows: activity,
      columns: ["block_time", "event", "project", "label", "token_symbol", "amount_usd", "blockchain", "tx_hash"],
      labels: { block_time: "Age", event: "Event", project: "Project", label: "Label", token_symbol: "Token", amount_usd: "Amount", blockchain: "Chain", tx_hash: "Transaction" },
      formats: { amount_usd: "currency_compact" },
      signedColumns: ["amount_usd"],
      relativeTimeColumns: ["block_time"],
      metric,
      emptyMessage: "No later ether.fi activity is available for this wallet in the selected period.",
    });
    bindIntelligenceCopyButtons(shell);
    body.appendChild(shell);
  }

  function renderIntelligenceMetric(state, metric) {
    const renderers = {
      top_referred_depositors: renderBarChart,
      referral_concentration: renderReferralConcentration,
      top_depositors: renderTable,
      recent_referral_deposits: renderTable,
      recent_etherfi_activity: renderTable,
      wallet_investigation: renderWalletInvestigation,
    };
    const renderer = renderers[metric.intelligence_component];
    if (!renderer) {
      renderMetricState(
        state,
        metric,
        "error",
        "Unsupported intelligence component.",
        `Studio cannot render “${metric.intelligence_component}”.`,
      );
      return;
    }
    renderer(state, metric);
  }

  function metricSourceNotice(state, metric) {
    const primaryMetadata = sourceMetadataForMetric(state, metric);
    const primarySource = sourceForMetric(state, metric);
    if (!isUsableSource(primarySource)) {
      return {
        kind: "unavailable",
        text: "Data unavailable",
        timestamp: "",
      };
    }
    if (primaryMetadata.snapshot_state === "previous") {
      const latestRefresh = primaryMetadata.latest_attempt_status === "partial"
        ? "latest refresh partially failed"
        : "latest refresh failed";
      return {
        kind: "previous",
        text: `Using previous snapshot · ${latestRefresh}`,
        timestamp: primaryMetadata.display_updated_at
          || primaryMetadata.data_updated_at
          || primaryMetadata.execution_finished_at
          || primaryMetadata.generated_at
          || "",
      };
    }
    if (
      primaryMetadata.stale
      || primaryMetadata.freshness_status === "stale"
    ) {
      const timestamp = (
        primaryMetadata.data_updated_at
        || primaryMetadata.execution_finished_at
        || primaryMetadata.generated_at
      );
      return {
        kind: "stale",
        text: timestamp
          ? `Stale data · result from ${longDate(timestamp)}`
          : "Stale data · refresh overdue",
        timestamp,
      };
    }
    if (
      primaryMetadata.delayed
      || primaryMetadata.freshness_status === "delayed"
    ) {
      return {
        kind: "delayed",
        text: "Refresh delayed · showing latest valid data",
        timestamp: primaryMetadata.data_updated_at
          || primaryMetadata.execution_finished_at
          || primaryMetadata.generated_at
          || "",
      };
    }
    if (!metric.sparkline_data_source) {
      return null;
    }
    const sparklineSource = sourceForMetric(
      state,
      metric,
      metric.sparkline_data_source,
    );
    const sparklineMetadata = sourceMetadataForMetric(
      state,
      metric,
      metric.sparkline_data_source,
    );
    if (!Array.isArray(sparklineSource)) {
      const code = sparklineSource && sparklineSource.code
        ? sparklineSource.code
        : sparklineMetadata.status;
      const reason = code === "failed"
        ? "query failed"
        : code === "missing_columns"
          ? "expected column missing"
          : code === "malformed"
            ? "data malformed"
            : "data unavailable";
      return {
        kind: "partial",
        text: `Trend unavailable · ${reason}`,
        timestamp: "",
      };
    }
    if (!sparklineSource.length) {
      return {
        kind: "partial",
        text: "Trend unavailable · no data",
        timestamp: "",
      };
    }
    if (sparklineMetadata.snapshot_state === "previous") {
      const latestRefresh = sparklineMetadata.latest_attempt_status === "partial"
        ? "latest refresh partially failed"
        : "latest refresh failed";
      return {
        kind: "previous",
        text: `Trend uses previous snapshot · ${latestRefresh}`,
        timestamp: sparklineMetadata.display_updated_at
          || sparklineMetadata.data_updated_at
          || sparklineMetadata.execution_finished_at
          || sparklineMetadata.generated_at
          || "",
      };
    }
    if (
      sparklineMetadata.stale
      || sparklineMetadata.freshness_status === "stale"
    ) {
      const timestamp = (
        sparklineMetadata.data_updated_at
        || sparklineMetadata.execution_finished_at
        || sparklineMetadata.generated_at
      );
      return {
        kind: "stale",
        text: timestamp
          ? `Trend data stale · result from ${longDate(timestamp)}`
          : "Trend data stale · refresh overdue",
        timestamp,
      };
    }
    if (
      sparklineMetadata.delayed
      || sparklineMetadata.freshness_status === "delayed"
    ) {
      return {
        kind: "delayed",
        text: "Trend refresh delayed · showing latest valid data",
        timestamp: sparklineMetadata.data_updated_at
          || sparklineMetadata.execution_finished_at
          || sparklineMetadata.generated_at
          || "",
      };
    }
    return null;
  }

  function updateMetricSourceNotice(state, metric) {
    const card = state.page.querySelector(`[data-studio-metric-id="${metric.id}"]`);
    if (!card) {
      return;
    }
    const existing = card.querySelector("[data-studio-source-notice]");
    if (existing) {
      existing.remove();
    }
    if (metric.compact_counter) {
      return;
    }
    const sourceNotice = metricSourceNotice(state, metric);
    if (!sourceNotice) {
      return;
    }
    const titleBlock = card.querySelector(".studio-metric-header > div:first-child");
    if (!titleBlock) {
      return;
    }
    const notice = createElement(
      card.ownerDocument,
      "p",
      "studio-source-state-note",
      sourceNotice.text,
    );
    notice.dataset.studioSourceNotice = sourceNotice.kind;
    notice.setAttribute("role", "status");
    if (sourceNotice.timestamp) {
      notice.title = (
        `Query result generated ${utcTimestampLabel(sourceNotice.timestamp)}`
      );
    }
    titleBlock.appendChild(notice);
  }

  function renderMetric(state, metric) {
    const card = state.page.querySelector(`[data-studio-metric-id="${metric.id}"]`);
    if (!card || card.hidden) {
      state.dirty.add(metric.id);
      return;
    }
    if (!state.data) {
      return;
    }
    card.classList.toggle(
      "studio-counter-compact",
      metric.visualization_type === "counter" && Boolean(metric.compact_counter),
    );
    const renderers = {
      counter: renderCounter,
      line: renderLineChart,
      bar: renderBarChart,
      sankey: renderSankey,
      table: renderTable,
    };
    const renderer = metric.intelligence_component
      ? renderIntelligenceMetric
      : renderers[metric.visualization_type];
    if (!renderer) {
      renderMetricState(
        state,
        metric,
        "error",
        "Unsupported visualization.",
        `Studio cannot render “${metric.visualization_type}”.`,
      );
      return;
    }
    renderer(state, metric);
    updateMetricSourceNotice(state, metric);
    state.rendered.add(metric.id);
    state.dirty.delete(metric.id);
  }

  function renderVisibleMetrics(state) {
    state.metrics.forEach((metric) => {
      const card = state.page.querySelector(`[data-studio-metric-id="${metric.id}"]`);
      if (card && !card.hidden && (
        !state.rendered.has(metric.id) || state.dirty.has(metric.id)
      )) {
        renderMetric(state, metric);
      }
    });
  }

  function localStorageForRoot() {
    try {
      return root && root.localStorage ? root.localStorage : null;
    } catch (error) {
      return null;
    }
  }

  function dashboardStateStorageKey(kind, dashboardId) {
    return `etherfi.studio.${safeFilename(kind)}.v1.${safeFilename(dashboardId)}`;
  }

  function currentStudioUrl() {
    if (!root || !root.location || typeof root.URL !== "function") {
      return null;
    }
    try {
      return new root.URL(root.location.href);
    } catch (error) {
      return null;
    }
  }

  function studioUrlParameter(name) {
    const url = currentStudioUrl();
    return url ? String(url.searchParams.get(name) || "") : "";
  }

  function updateStudioUrlParameter(name, value) {
    const url = currentStudioUrl();
    if (!url || !root.history || typeof root.history.replaceState !== "function") {
      return false;
    }
    if (value) {
      url.searchParams.set(name, value);
    } else {
      url.searchParams.delete(name);
    }
    root.history.replaceState(root.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    return true;
  }

  function storedDashboardValue(key) {
    const storage = localStorageForRoot();
    if (!storage) {
      return "";
    }
    try {
      return String(storage.getItem(key) || "");
    } catch (error) {
      return "";
    }
  }

  function persistDashboardValue(key, value) {
    const storage = localStorageForRoot();
    if (!storage) {
      return;
    }
    try {
      if (value) {
        storage.setItem(key, String(value));
      } else {
        storage.removeItem(key);
      }
    } catch (error) {
      // Storage is optional; URL and in-memory state remain available.
    }
  }

  function restoredDashboardRange(config, storageKey) {
    const explicit = String(
      studioUrlParameter("period") || studioUrlParameter("range"),
    ).toLocaleUpperCase("en");
    if (RANGE_OPTIONS.includes(explicit)) {
      return explicit;
    }
    const stored = storedDashboardValue(storageKey).toLocaleUpperCase("en");
    if (RANGE_OPTIONS.includes(stored)) {
      return stored;
    }
    const configured = String(
      config && config.dashboard && config.dashboard.default_date_range || "ALL",
    ).toLocaleUpperCase("en");
    return RANGE_OPTIONS.includes(configured) ? configured : "ALL";
  }

  function restoredRecentWallets(storageKey) {
    const stored = storedDashboardValue(storageKey);
    if (!stored) {
      return [];
    }
    try {
      const parsed = JSON.parse(stored);
      return Array.isArray(parsed)
        ? parsed.map(normalizeWalletAddress).filter(Boolean).slice(0, 5)
        : [];
    } catch (error) {
      return [];
    }
  }

  function persistRecentWallets(state) {
    const storage = localStorageForRoot();
    if (!storage) {
      return;
    }
    try {
      storage.setItem(
        state.recentWalletsKey,
        JSON.stringify((state.recentWallets || []).slice(0, 5)),
      );
    } catch (error) {
      // Recent-wallet shortcuts are optional.
    }
  }

  function visibilityStorageKey(dashboardId, metrics) {
    const registryIdentity = (Array.isArray(metrics) ? metrics : [])
      .map((metric) => (
        `${String(metric && metric.id || "")}:${metric && metric.default_visible ? "1" : "0"}`
      ))
      .sort((left, right) => left.localeCompare(right, "en"))
      .join("\u0000");
    let hash = 2166136261;
    for (let index = 0; index < registryIdentity.length; index += 1) {
      hash ^= registryIdentity.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const signature = (hash >>> 0).toString(16).padStart(8, "0");
    return `etherfi.studio.visibility.v2.${safeFilename(dashboardId)}.${signature}`;
  }

  function visibilitySectionIds(metrics) {
    return Array.from(new Set(
      (Array.isArray(metrics) ? metrics : [])
        .map((metric) => String(metric && metric.section || "").trim())
        .filter(Boolean),
    ));
  }

  function visibilityDisclosureStorageKey(dashboardId, metrics) {
    const sections = visibilitySectionIds(metrics).join("\u0000");
    let hash = 2166136261;
    for (let index = 0; index < sections.length; index += 1) {
      hash ^= sections.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    const signature = (hash >>> 0).toString(16).padStart(8, "0");
    return `etherfi.studio.visibility-sections.v1.${safeFilename(dashboardId)}.${signature}`;
  }

  function visibilityDisclosureModel(expandedSections, section) {
    const current = new Set(
      (Array.isArray(expandedSections) ? expandedSections : [])
        .map(String)
        .filter(Boolean),
    );
    const id = String(section || "").trim();
    if (!id) {
      return [...current];
    }
    if (current.has(id)) {
      current.delete(id);
    } else {
      current.add(id);
    }
    return [...current];
  }

  function restoredVisibilityDisclosures(state) {
    const sections = visibilitySectionIds(state.metrics);
    const defaults = sections.length ? [sections[0]] : [];
    const storage = localStorageForRoot();
    if (!storage) {
      return new Set(defaults);
    }
    try {
      const stored = JSON.parse(storage.getItem(state.visibilityDisclosureKey));
      if (!Array.isArray(stored)) {
        return new Set(defaults);
      }
      const valid = new Set(sections);
      return new Set(stored.filter((section) => valid.has(section)));
    } catch (error) {
      return new Set(defaults);
    }
  }

  function persistVisibilityDisclosures(state) {
    const storage = localStorageForRoot();
    if (!storage) {
      return;
    }
    const expanded = visibilitySectionIds(state.metrics)
      .filter((section) => state.expandedVisibilitySections.has(section));
    try {
      storage.setItem(state.visibilityDisclosureKey, JSON.stringify(expanded));
    } catch (error) {
      // Storage can be blocked without affecting the panel session.
    }
  }

  function applyVisibilityDisclosures(state) {
    state.page.querySelectorAll("[data-visibility-disclosure]").forEach((button) => {
      const section = button.dataset.visibilityDisclosure;
      const expanded = state.expandedVisibilitySections.has(section);
      button.setAttribute("aria-expanded", String(expanded));
      const ariaLabel = button.getAttribute("aria-label") || "";
      if (/^(expand|collapse)\b/i.test(ariaLabel)) {
        button.setAttribute(
          "aria-label",
          ariaLabel.replace(/^(expand|collapse)\b/i, expanded ? "Collapse" : "Expand"),
        );
      }
      state.page.querySelectorAll("[data-visibility-list]").forEach((list) => {
        if (list.dataset.visibilityList === section) {
          list.hidden = !expanded;
        }
      });
    });
  }

  function restoredVisibility(state) {
    const defaults = state.metrics
      .filter((metric) => metric.default_visible)
      .map((metric) => metric.id);
    const storage = localStorageForRoot();
    if (!storage) {
      return new Set(defaults);
    }
    try {
      const stored = JSON.parse(storage.getItem(state.visibilityKey));
      if (!Array.isArray(stored)) {
        return new Set(defaults);
      }
      const valid = new Set(state.metrics.map((metric) => metric.id));
      return new Set(stored.filter((id) => valid.has(id)));
    } catch (error) {
      return new Set(defaults);
    }
  }

  function persistVisibility(state) {
    const storage = localStorageForRoot();
    if (!storage) {
      return;
    }
    const ordered = state.metrics
      .map((metric) => metric.id)
      .filter((id) => state.visible.has(id));
    try {
      storage.setItem(state.visibilityKey, JSON.stringify(ordered));
    } catch (error) {
      // Storage can be blocked without affecting the dashboard session.
    }
  }

  function metricsInSection(state, section) {
    return state.metrics.filter((metric) => metric.section === section);
  }

  function updateVisibilityControls(state) {
    state.page.querySelectorAll("[data-visibility-metric]").forEach((checkbox) => {
      checkbox.checked = state.visible.has(checkbox.dataset.visibilityMetric);
    });
    state.page.querySelectorAll("[data-visibility-group]").forEach((checkbox) => {
      const groupMetrics = metricsInSection(state, checkbox.dataset.visibilityGroup);
      const selected = groupMetrics.filter((metric) => state.visible.has(metric.id)).length;
      checkbox.checked = groupMetrics.length > 0 && selected === groupMetrics.length;
      checkbox.indeterminate = selected > 0 && selected < groupMetrics.length;
      checkbox.setAttribute(
        "aria-checked",
        checkbox.indeterminate ? "mixed" : String(checkbox.checked),
      );
      const count = checkbox.closest("legend") && checkbox.closest("legend").querySelector("small");
      if (count) {
        count.textContent = `${selected}/${groupMetrics.length}`;
      }
    });
    const counter = state.page.querySelector("[data-visible-count]");
    if (counter) {
      counter.textContent = String(state.visible.size);
    }
  }

  function scheduleChartResize(state) {
    if (!root || typeof root.setTimeout !== "function") {
      return;
    }
    root.clearTimeout(state.resizeTimer);
    state.resizeTimer = root.setTimeout(() => {
      state.charts.forEach((chart) => {
        try {
          chart.resize();
        } catch (error) {
          // Ignore a chart disposed during the same layout transition.
        }
      });
    }, 240);
  }

  function applyVisibility(state, persist) {
    state.metrics.forEach((metric) => {
      const card = state.page.querySelector(`[data-studio-metric-id="${metric.id}"]`);
      if (!card) {
        return;
      }
      const visible = state.visible.has(metric.id);
      const wasHidden = card.hidden;
      card.hidden = !visible;
      card.dataset.studioVisible = String(visible);
      if (visible && wasHidden && state.data) {
        state.dirty.add(metric.id);
      }
    });
    state.page.querySelectorAll("[data-studio-section]").forEach((section) => {
      const visibleCard = [...section.querySelectorAll("[data-studio-metric-id]")]
        .some((card) => !card.hidden);
      section.hidden = !visibleCard;
    });
    updateSectionNavigation(state);
    const noMetrics = state.page.querySelector("[data-no-visible-metrics]");
    if (noMetrics) {
      noMetrics.hidden = state.visible.size !== 0;
    }
    updateVisibilityControls(state);
    if (persist) {
      persistVisibility(state);
    }
    if (!state.page.querySelector("[data-export-metric]")) {
      state.exportSelected = new Set(
        state.metrics
          .filter((metric) => metric.is_exportable && state.visible.has(metric.id))
          .map((metric) => metric.id),
      );
      updateExportControls(state);
    }
    renderVisibleMetrics(state);
    scheduleChartResize(state);
  }

  function bindVisibility(state) {
    applyVisibilityDisclosures(state);
    state.page.querySelectorAll("[data-visibility-disclosure]").forEach((button) => {
      button.addEventListener("click", () => {
        state.expandedVisibilitySections = new Set(visibilityDisclosureModel(
          [...state.expandedVisibilitySections],
          button.dataset.visibilityDisclosure,
        ));
        applyVisibilityDisclosures(state);
        persistVisibilityDisclosures(state);
      });
    });
    state.page.querySelectorAll("[data-visibility-metric]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const id = checkbox.dataset.visibilityMetric;
        if (checkbox.checked) {
          state.visible.add(id);
        } else {
          state.visible.delete(id);
        }
        applyVisibility(state, true);
      });
    });
    state.page.querySelectorAll("[data-visibility-group]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        metricsInSection(state, checkbox.dataset.visibilityGroup).forEach((metric) => {
          if (checkbox.checked) {
            state.visible.add(metric.id);
          } else {
            state.visible.delete(metric.id);
          }
        });
        applyVisibility(state, true);
      });
    });
    state.page.querySelectorAll("[data-visibility-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.visibilityAction;
        if (action === "show-all") {
          state.visible = new Set(state.metrics.map((metric) => metric.id));
        } else if (action === "hide-all") {
          state.visible = new Set();
        } else if (action === "reset") {
          state.visible = new Set(
            state.metrics
              .filter((metric) => metric.default_visible)
              .map((metric) => metric.id),
          );
        }
        applyVisibility(state, true);
      });
    });
  }

  function updateExportControls(state) {
    state.page.querySelectorAll("[data-export-metric]").forEach((checkbox) => {
      checkbox.checked = state.exportSelected.has(checkbox.dataset.exportMetric);
    });
    state.page.querySelectorAll("[data-export-group]").forEach((checkbox) => {
      const metrics = state.metrics.filter((metric) => (
        metric.section === checkbox.dataset.exportGroup && metric.is_exportable
      ));
      const selected = metrics.filter((metric) => state.exportSelected.has(metric.id)).length;
      checkbox.checked = metrics.length > 0 && selected === metrics.length;
      checkbox.indeterminate = selected > 0 && selected < metrics.length;
      checkbox.setAttribute(
        "aria-checked",
        checkbox.indeterminate ? "mixed" : String(checkbox.checked),
      );
      const count = checkbox.closest("legend") && checkbox.closest("legend").querySelector("small");
      if (count) {
        count.textContent = `${selected}/${metrics.length}`;
      }
    });
    const count = state.page.querySelector("[data-export-count]");
    if (count && !count.hasAttribute("data-visible-count")) {
      count.textContent = String(state.exportSelected.size);
    }
    const button = state.page.querySelector("[data-export-download]");
    if (button) {
      button.disabled = state.exportSelected.size === 0 || !state.data;
      button.setAttribute("aria-disabled", String(button.disabled));
    }
  }

  function metricGeneratedDate(state, metric) {
    const sourceMetadata = sourceMetadataForMetric(state, metric);
    const dashboardMetadata = state && state.data && state.data.meta
      ? state.data.meta
      : {};
    return dateStamp(
      sourceMetadata.display_updated_at
      || dashboardMetadata.display_updated_at
      || sourceMetadata.data_updated_at
      || sourceMetadata.execution_finished_at
      || sourceMetadata.generated_at
      || dashboardMetadata.data_updated_at
      || dashboardMetadata.generated_at
      || dashboardMetadata.last_refreshed,
    ) || "unknown-date";
  }

  function metricExportFilename(state, metric) {
    if (metric && metric.export_slug) {
      const period = (metric.period_key_column || metric.momentum_chart || metric.growth_chart)
        && state && state.activeRange
        ? `-${safeFilename(String(state.activeRange).toLocaleLowerCase("en"))}`
        : "";
      return `${safeFilename(metric.export_slug)}${period}-${metricGeneratedDate(state, metric)}.csv`;
    }
    const dashboard = state && state.config && state.config.dashboard
      ? state.config.dashboard
      : {};
    const dashboardName = dashboard.slug || dashboard.id || "studio";
    return [
      safeFilename(dashboardName),
      safeFilename(metric && metric.id ? metric.id : "metric"),
      metricGeneratedDate(state, metric),
    ].join("-") + ".csv";
  }

  function dashboardGeneratedDate(state, metrics) {
    const candidates = [];
    (Array.isArray(metrics) ? metrics : []).forEach((metric) => {
      const metadata = sourceMetadataForMetric(state, metric);
      candidates.push(
        metadata.display_updated_at
        || metadata.data_updated_at
        || metadata.execution_finished_at
        || metadata.generated_at,
      );
    });
    const sourceTimestamp = latestTimestamp(candidates);
    const dashboardMetadata = state && state.data && state.data.meta
      ? state.data.meta
      : {};
    return dateStamp(
      dashboardMetadata.display_updated_at
      || dashboardMetadata.data_updated_at
      || sourceTimestamp
      || dashboardMetadata.generated_at
      || dashboardMetadata.last_refreshed,
    ) || "unknown-date";
  }

  function dashboardExportFilename(state, metrics) {
    const dashboard = state && state.config && state.config.dashboard
      ? state.config.dashboard
      : {};
    return `${safeFilename(dashboard.slug || dashboard.id || "studio")}`
      + `-studio-${dashboardGeneratedDate(state, metrics)}.zip`;
  }

  function metricExportColumns(metric) {
    const configured = Array.isArray(metric && metric.export_columns)
      ? metric.export_columns
      : metric && metric.columns;
    return uniqueColumns(configured);
  }

  function metricExportColumnPlan(metric) {
    const aliases = metric && metric.export_column_aliases
      && typeof metric.export_column_aliases === "object"
      && !Array.isArray(metric.export_column_aliases)
      ? metric.export_column_aliases
      : {};
    return metricExportColumns(metric).map((source) => ({
      source,
      output: typeof aliases[source] === "string" && aliases[source].trim()
        ? aliases[source].trim()
        : source,
    }));
  }

  function metricExportRows(state, metric, source, plan) {
    const periodColumn = metric && metric.period_key_column;
    const rows = periodColumn
      ? [selectPeriodRow(source, metric, state && state.activeRange)]
      : source.slice();
    const metadata = sourceMetadataForMetric(state, metric);
    const sourceLastUpdated = metadata.source_last_updated
      || metadata.data_updated_at
      || metadata.execution_finished_at
      || "";
    const selectedPeriod = String(state && state.activeRange || "");
    const requestedPeriodKey = periodKeyForMetric(metric, selectedPeriod);
    return rows.map((sourceRow) => {
      const row = sourceRow && typeof sourceRow === "object" ? sourceRow : {};
      const projected = {};
      plan.forEach(({ source: sourceColumn, output }) => {
        if (periodColumn && sourceColumn === periodColumn && output === "period") {
          projected[output] = selectedPeriod;
          return;
        }
        if (sourceColumn === "source_last_updated") {
          projected[output] = sourceLastUpdated;
          return;
        }
        if (
          !Object.prototype.hasOwnProperty.call(row, sourceColumn)
          || isNil(row[sourceColumn])
        ) {
          projected[output] = 0;
          counterFallbackWarning(
            state,
            metric,
            requestedPeriodKey,
            sourceColumn,
            sourceRow ? "missing metric column or value" : "missing period key",
          );
          return;
        }
        projected[output] = row[sourceColumn];
      });
      return projected;
    });
  }

  function metricCsvEntry(state, metric) {
    if (metric && metric.intelligence_component) {
      const source = intelligenceSource(state, metric);
      if (!isUsableSource(source)) {
        return null;
      }
      const component = metric.intelligence_component;
      let rows = [];
      let columns = [];
      if (component === "top_referred_depositors") {
        const limit = state.topN.get(metric.id) || Number(metric.default_top_n) || 10;
        rows = intelligenceRankedWallets(source).slice(0, limit);
        columns = Array.isArray(metric.intelligence_export_columns)
          ? metric.intelligence_export_columns
          : ["rank", "address", "total_referral_deposits_usd", "attributed_tvl_usd", "retention_rate", "products_deposited", "depositor_type"];
      } else if (component === "referral_concentration") {
        const defaultMeasure = metric.default_concentration_measure === "attributed_tvl"
          ? "attributed_tvl"
          : "referral_deposits";
        const measure = state.intelligenceMeasures.get(metric.id) || defaultMeasure;
        const model = concentrationModel(source, measure);
        rows = [
          ...model.tiers.map((tier) => ({
            record_type: "concentration_tier",
            measure,
            tier: `Top ${tier.topN}`,
            rank: "",
            address: "",
            value_usd: tier.valueUsd,
            share: tier.share,
          })),
          ...model.ranking.map((row, index) => ({
            record_type: "address_ranking",
            measure,
            tier: "",
            rank: row.rank || index + 1,
            address: row.address,
            value_usd: row.value_usd
              ?? row.total_referral_deposits_usd
              ?? row.attributed_tvl_usd,
            share: row.share ?? "",
          })),
        ];
        columns = ["record_type", "measure", "tier", "rank", "address", "value_usd", "share"];
      } else if ([
        "top_depositors",
        "recent_referral_deposits",
        "recent_etherfi_activity",
      ].includes(component)) {
        rows = rowsForMetric(state, metric);
        columns = Array.isArray(metric.export_columns)
          ? metric.export_columns
          : Array.isArray(metric.table_columns) ? metric.table_columns
            : Array.isArray(metric.intelligence_columns) ? metric.intelligence_columns
              : metric.columns || [];
      } else if (component === "wallet_investigation") {
        const wallet = intelligenceWalletForAddress(source, state.selectedWallet);
        if (!wallet) {
          return null;
        }
        rows = [
          { record_type: "wallet_summary", ...wallet, positions: "", referral_deposits: "", activity: "" },
          ...intelligenceWalletCollection(wallet, ["positions"]).map((row) => ({ record_type: "current_position", address: wallet.address, ...row })),
          ...intelligenceWalletCollection(wallet, ["referral_deposits", "deposits"]).map((row) => ({ record_type: "referral_deposit", address: wallet.address, ...row })),
          ...intelligenceWalletCollection(wallet, ["activity", "activities"]).map((row) => ({ record_type: "etherfi_activity", address: wallet.address, ...row })),
        ];
        columns = inferredColumns(rows);
      }
      return Array.isArray(rows) && rows.length && columns.length ? {
        name: metricExportFilename(state, metric),
        data: buildCsv(rows, columns),
      } : null;
    }
    const source = rawRowsForMetric(state, metric);
    if (Array.isArray(source) && metric && metric.momentum_chart) {
      const selection = state.momentumSelections.get(metric.id) || {
        granularity: metric.momentum_chart.default_granularity,
        filter: "all",
      };
      const model = momentumChartModel(source, metric, {
        ...selection,
        activeRange: state.activeRange,
        referenceDate: state.referenceDate,
      });
      const columns = metric.momentum_chart.export_columns.slice();
      return model ? {
        name: metricExportFilename(state, metric),
        data: buildCsv(model.exportRows, columns),
      } : null;
    }
    if (Array.isArray(source) && metric && metric.growth_chart) {
      const config = metric.growth_chart;
      const selection = state.growthSelections.get(metric.id) || {
        granularity: config.default_granularity || "weekly",
        view: config.default_view || growthChartViews(metric)[0] && growthChartViews(metric)[0].id,
      };
      const model = growthChartModel(source, metric, {
        ...selection,
        activeRange: state.activeRange,
        referenceDate: state.referenceDate,
      });
      const columns = Array.isArray(config.export_columns)
        ? config.export_columns.slice()
        : [];
      return model && columns.length ? {
        name: metricExportFilename(state, metric),
        data: buildCsv(growthProjectedExportRows(model, config), columns),
      } : null;
    }
    const plan = metricExportColumnPlan(metric);
    if (!Array.isArray(source) || !plan.length) {
      return null;
    }
    const rows = metricExportRows(state, metric, source, plan);
    const columns = plan.map(({ output }) => output);
    return {
      name: metricExportFilename(state, metric),
      data: buildCsv(rows, columns),
    };
  }

  function selectedMetricCsvEntries(state, metrics) {
    const entries = [];
    const unavailable = [];
    (Array.isArray(metrics) ? metrics : []).forEach((metric) => {
      const entry = metricCsvEntry(state, metric);
      if (entry) {
        entries.push(entry);
      } else {
        unavailable.push(
          metric && (metric.export_name || metric.name || metric.id) || "Unknown metric",
        );
      }
    });
    return { entries, unavailable };
  }

  function stringList(value) {
    return Array.isArray(value)
      ? value.filter((item) => typeof item === "string" && item.trim())
        .map((item) => item.trim())
      : [];
  }

  function repositoryFileUrl(path, config) {
    const value = String(path || "").trim();
    if (!value || value.includes("..") || !/^[A-Za-z0-9._/-]+$/.test(value)) {
      return "";
    }
    const dashboard = config && config.dashboard || {};
    const configuredBase = config && (
      config.repository_file_url_base || config.repositoryFileUrlBase
    ) || dashboard.repository_file_url_base || dashboard.repositoryFileUrlBase;
    const base = String(configuredBase || STUDIO_REPOSITORY_FILE_BASE);
    return `${base.replace(/\/*$/, "/")}${value.replace(/^\/*/, "")}`;
  }

  function methodologyValidation(summary) {
    const details = summary && typeof summary === "object" && !Array.isArray(summary)
      ? summary
      : {};
    const items = [];
    if (
      !isNil(details.total_referral_value_usd)
      && !isNil(details.total_attributed_value_usd)
      && !isNil(details.total_exited_value_usd)
    ) {
      items.push(
        `Referral value ${formatValue(details.total_referral_value_usd, "currency")}`
        + ` reconciles to active attribution ${formatValue(details.total_attributed_value_usd, "currency")}`
        + ` plus exited value ${formatValue(details.total_exited_value_usd, "currency")}.`,
      );
    }
    if (!isNil(details.reconciliation_delta_usd)) {
      items.push(
        `USD reconciliation delta: ${formatValue(details.reconciliation_delta_usd, "currency")}.`,
      );
    }
    if (!isNil(details.invalid_group_count)) {
      items.push(`Invalid attribution groups: ${details.invalid_group_count}.`);
    }
    if (!isNil(details.source_rows)) {
      items.push(`Validated source rows: ${details.source_rows}.`);
    }
    return items;
  }

  function methodologyDetails(metric, sourceMetadata, config) {
    const source = sourceMetadata && typeof sourceMetadata === "object"
      ? sourceMetadata
      : {};
    const methodology = metric && metric.methodology && typeof metric.methodology === "object"
      ? metric.methodology
      : {};
    const transformation = metric && metric.transformation
      && typeof metric.transformation === "object"
      ? metric.transformation
      : {};
    const summary = source.transformation_summary && typeof source.transformation_summary === "object"
      ? source.transformation_summary
      : {};
    const configuredValidation = stringList(methodology.validation);
    const validation = [
      ...configuredValidation,
      ...methodologyValidation(summary),
    ];
    const warnings = stringList(
      source.data_quality_warnings
      || source.transformation_warnings
      || source.warnings,
    );
    return {
      title: String(
        methodology.title
        || `${metric && (metric.name || metric.id) || "Metric"} methodology`,
      ),
      description: String(methodology.description || ""),
      methodologyId: String(
        source.methodology_id || transformation.methodology_id || transformation.id || "",
      ),
      methodologyVersion: String(
        source.methodology_version || transformation.version || "",
      ),
      queryId: String(source.query_id || metric && metric.query_id || ""),
      queryUrl: String(metric && metric.query_url || source.query_url || ""),
      queryUrls: Array.from(new Set([
        metric && metric.query_url,
        ...(Array.isArray(metric && metric.related_query_urls)
          ? metric.related_query_urls.map((entry) => (
            entry && typeof entry === "object" ? entry.url : entry
          ))
          : []),
      ].map((value) => String(value || "").trim()).filter(Boolean))),
      executionId: String(
        source.source_execution_id || source.execution_id || "",
      ),
      sourceLastUpdated: String(
        source.source_last_updated
        || source.data_updated_at
        || source.execution_finished_at
        || "",
      ),
      generatedAt: String(source.generated_at || ""),
      freshnessStatus: String(source.freshness_status || ""),
      assumptions: stringList(methodology.definitions || methodology.assumptions),
      metricDefinitions: stringList(methodology.metric_definitions),
      selectedPeriodLogic: stringList(methodology.selected_period_logic),
      businessRules: stringList(methodology.business_rules),
      allocationRules: stringList(methodology.allocation_rules),
      validation,
      limitations: [...stringList(methodology.notes || methodology.limitations), ...warnings],
      scriptUrl: repositoryFileUrl(transformation.script_path, config),
      testsUrl: repositoryFileUrl(transformation.tests_path, config),
      scriptPath: String(transformation.script_path || ""),
      testsPath: String(transformation.tests_path || ""),
    };
  }

  function appendMethodologyList(scope, container, heading, items) {
    if (!items.length) {
      return;
    }
    const section = createElement(scope, "section", "studio-methodology-section");
    section.appendChild(createElement(scope, "h3", "", heading));
    const list = createElement(scope, "ul");
    items.forEach((item) => {
      list.appendChild(createElement(scope, "li", "", item));
    });
    section.appendChild(list);
    container.appendChild(section);
  }

  function closeMethodologyDialog(dialog) {
    if (!dialog) {
      return;
    }
    if (typeof dialog.close === "function" && dialog.hasAttribute("open")) {
      dialog.close();
      return;
    }
    dialog.removeAttribute("open");
    dialog.setAttribute("aria-hidden", "true");
    const trigger = dialog.__studioReturnFocus;
    if (trigger && typeof trigger.focus === "function" && trigger.isConnected) {
      trigger.focus();
    }
  }

  function methodologyDialog(state) {
    let dialog = state.page.querySelector("[data-studio-methodology-dialog]");
    if (!dialog) {
      dialog = createElement(state.page.ownerDocument, "dialog", "studio-methodology-dialog");
      dialog.dataset.studioMethodologyDialog = "";
      state.page.appendChild(dialog);
    }
    dialog.classList.add("studio-methodology-dialog");
    dialog.id = `studio-methodology-${safeFilename(state.config.dashboard.id)}`;
    if (dialog.dataset.methodologyBound !== "true") {
      dialog.dataset.methodologyBound = "true";
      dialog.addEventListener("click", (event) => {
        if (
          event.target === dialog
          || (event.target.closest && event.target.closest("[data-methodology-close]"))
        ) {
          closeMethodologyDialog(dialog);
        }
      });
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        closeMethodologyDialog(dialog);
      });
      dialog.addEventListener("close", () => {
        const trigger = dialog.__studioReturnFocus;
        if (trigger && typeof trigger.focus === "function" && trigger.isConnected) {
          trigger.focus();
        }
      });
      dialog.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          closeMethodologyDialog(dialog);
          return;
        }
        if (event.key !== "Tab" || typeof dialog.querySelectorAll !== "function") {
          return;
        }
        const focusable = [...dialog.querySelectorAll(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )].filter((element) => !element.hidden);
        if (!focusable.length) {
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && state.page.ownerDocument.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && state.page.ownerDocument.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });
    }
    return dialog;
  }

  function appendProvenance(scope, container, details) {
    const sourceExecution = details.executionId.startsWith("fixture-")
      ? "Local validation fixture"
      : details.executionId;
    const values = [
      ["Method", [details.methodologyId, details.methodologyVersion]
        .filter(Boolean).join(" · v")],
      ["Source execution", sourceExecution],
      ["Source last updated", details.sourceLastUpdated
        ? utcTimestampLabel(details.sourceLastUpdated) : ""],
      ["Snapshot generated", details.generatedAt
        ? utcTimestampLabel(details.generatedAt) : ""],
      ["Freshness", details.freshnessStatus],
    ].filter((entry) => entry[1]);
    if (!values.length) {
      return;
    }
    const provenance = createElement(scope, "dl", "studio-methodology-provenance");
    values.forEach(([label, value]) => {
      const item = createElement(
        scope,
        "div",
        "studio-methodology-provenance-item",
      );
      item.append(
        createElement(scope, "dt", "", label),
        createElement(scope, "dd", "", value),
      );
      provenance.appendChild(item);
    });
    container.appendChild(provenance);
  }

  function appendMethodologyLinks(scope, container, details) {
    const queryLinks = (Array.isArray(details.queryUrls) && details.queryUrls.length
      ? details.queryUrls
      : [details.queryUrl]
    ).filter(Boolean).map((href, index) => ({
      label: "View Dune Query",
      href,
      ariaLabel: `Open Dune source query ${index + 1} in a new tab`,
    }));
    const links = [
      ...queryLinks,
      { label: "Python transformation", href: details.scriptUrl },
      { label: "Focused tests", href: details.testsUrl },
    ].filter((entry) => entry.href);
    if (!links.length) {
      return;
    }
    const actions = createElement(scope, "div", "studio-methodology-links");
    const actionList = createElement(scope, "div", "studio-methodology-link-list");
    links.forEach(({ label, href, ariaLabel }) => {
      const link = createElement(scope, "a", "", label);
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      if (ariaLabel) {
        link.setAttribute("aria-label", ariaLabel);
      }
      actionList.appendChild(link);
    });
    actions.appendChild(actionList);
    container.appendChild(actions);
  }

  function openMethodologyDialog(state, metric, trigger) {
    const sourceRows = sourceForMetric(state, metric);
    const rowProvenance = Array.isArray(sourceRows) && sourceRows.length
      ? sourceRows[0]
      : {};
    const details = methodologyDetails(
      metric,
      { ...rowProvenance, ...sourceMetadataForMetric(state, metric) },
      state.config,
    );
    const dialog = methodologyDialog(state);
    const scope = dialog.ownerDocument;
    const panel = createElement(scope, "div", "studio-methodology-panel");
    const header = createElement(scope, "header", "studio-methodology-header");
    const heading = createElement(scope, "div");
    heading.append(
      createElement(
        scope,
        "p",
        "studio-kicker",
        metric.momentum_chart ? "Metric methodology" : "Attribution methodology",
      ),
      createElement(scope, "h2", "", details.title),
    );
    const close = createElement(scope, "button", "studio-methodology-close", "Close");
    close.type = "button";
    close.dataset.methodologyClose = "";
    close.setAttribute("aria-label", "Close methodology");
    header.append(heading, close);
    panel.appendChild(header);
    const content = createElement(scope, "div", "studio-methodology-content");
    content.dataset.methodologyContent = "";
    if (details.description) {
      content.appendChild(createElement(
        scope,
        "p",
        "studio-methodology-description",
        details.description,
      ));
    }
    appendProvenance(scope, content, details);
    appendMethodologyList(scope, content, "Metric definitions", details.metricDefinitions);
    appendMethodologyList(scope, content, "Selected-period logic", details.selectedPeriodLogic);
    appendMethodologyList(scope, content, "Definitions and assumptions", details.assumptions);
    appendMethodologyList(scope, content, "Business rules", details.businessRules);
    appendMethodologyList(scope, content, "Allocation rules", details.allocationRules);
    appendMethodologyList(scope, content, "Validation", details.validation);
    appendMethodologyList(scope, content, "Limitations and data quality", details.limitations);
    appendMethodologyLinks(scope, content, details);
    panel.appendChild(content);
    dialog.replaceChildren(panel);
    dialog.__studioReturnFocus = trigger;
    dialog.removeAttribute("aria-hidden");
    dialog.setAttribute("aria-labelledby", `${dialog.id}-title`);
    const title = header.querySelector("h2");
    if (title) {
      title.id = `${dialog.id}-title`;
    }
    if (typeof dialog.showModal === "function") {
      if (!dialog.hasAttribute("open")) {
        dialog.showModal();
      }
    } else {
      dialog.setAttribute("open", "");
      dialog.setAttribute("role", "dialog");
      dialog.setAttribute("aria-modal", "true");
    }
    close.focus();
    return dialog;
  }

  function bindMethodology(state) {
    state.page.querySelectorAll(".studio-source-link, [data-methodology-open]")
      .forEach((trigger) => {
        const card = trigger.closest && trigger.closest("[data-studio-metric-id]");
        const metricId = trigger.dataset.methodologyOpen
          || card && card.dataset.studioMetricId;
        const metric = metricId && state.metricsById.get(metricId);
        if (!metric || !metric.methodology) {
          return;
        }
        trigger.dataset.methodologyOpen = metric.id;
        trigger.setAttribute("aria-haspopup", "dialog");
        trigger.setAttribute(
          "aria-controls",
          `studio-methodology-${safeFilename(state.config.dashboard.id)}`,
        );
        trigger.addEventListener("click", (event) => {
          event.preventDefault();
          openMethodologyDialog(state, metric, trigger);
        });
      });
  }

  function setExportFeedback(state, message, kind) {
    const feedback = state.page.querySelector("[data-export-feedback]");
    if (!feedback) {
      return;
    }
    feedback.textContent = message || "";
    feedback.dataset.feedbackKind = kind || "";
  }

  function downloadBlob(blob, filename) {
    if (!root || !root.URL || typeof root.URL.createObjectURL !== "function") {
      return false;
    }
    const url = root.URL.createObjectURL(blob);
    const anchor = root.document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.hidden = true;
    root.document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    root.setTimeout(() => root.URL.revokeObjectURL(url), 1000);
    return true;
  }

  function downloadMetric(state, metric) {
    const entry = metricCsvEntry(state, metric);
    const exportName = metric.export_name || metric.name;
    if (!entry) {
      setExportFeedback(state, `${exportName} is unavailable for export.`, "error");
      return false;
    }
    const BlobConstructor = root && root.Blob;
    if (!BlobConstructor) {
      setExportFeedback(state, "This browser cannot create local downloads.", "error");
      return false;
    }
    const downloaded = downloadBlob(
      new BlobConstructor([entry.data], { type: "text/csv;charset=utf-8" }),
      entry.name,
    );
    setExportFeedback(
      state,
      downloaded ? `Downloaded ${exportName} as CSV.` : "The download could not be started.",
      downloaded ? "success" : "error",
    );
    return downloaded;
  }

  function downloadSelected(state) {
    const selected = state.metrics.filter((metric) => (
      metric.is_exportable && state.exportSelected.has(metric.id)
    ));
    if (!selected.length) {
      setExportFeedback(state, "Select at least one metric to export.", "error");
      return;
    }
    setExportFeedback(state, "Preparing selected metric files…", "progress");
    const run = () => {
      const selection = selectedMetricCsvEntries(state, selected);
      if (selection.unavailable.length) {
        setExportFeedback(
          state,
          `ZIP not created. Unavailable: ${selection.unavailable.join(", ")}.`,
          "error",
        );
        return;
      }
      const entries = selection.entries;
      if (!entries.length) {
        setExportFeedback(state, "The selected metrics have no exportable rows.", "error");
        return;
      }
      try {
        const bytes = createZip(entries);
        const BlobConstructor = root && root.Blob;
        if (!BlobConstructor) {
          throw new Error("Local Blob downloads are unavailable.");
        }
        const filename = dashboardExportFilename(state, selected);
        const downloaded = downloadBlob(
          new BlobConstructor([bytes], { type: "application/zip" }),
          filename,
        );
        setExportFeedback(
          state,
          downloaded
            ? `Downloaded ${entries.length} CSV ${entries.length === 1 ? "file" : "files"} in one ZIP.`
            : "The download could not be started.",
          downloaded ? "success" : "error",
        );
      } catch (error) {
        setExportFeedback(
          state,
          error && error.message ? error.message : "The ZIP could not be created.",
          "error",
        );
      }
    };
    if (root && typeof root.requestAnimationFrame === "function") {
      root.requestAnimationFrame(run);
    } else {
      run();
    }
  }

  function bindExports(state) {
    state.page.querySelectorAll("[data-export-metric]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const id = checkbox.dataset.exportMetric;
        if (checkbox.checked) {
          state.exportSelected.add(id);
        } else {
          state.exportSelected.delete(id);
        }
        updateExportControls(state);
      });
    });
    state.page.querySelectorAll("[data-export-group]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        state.metrics
          .filter((metric) => (
            metric.is_exportable && metric.section === checkbox.dataset.exportGroup
          ))
          .forEach((metric) => {
            if (checkbox.checked) {
              state.exportSelected.add(metric.id);
            } else {
              state.exportSelected.delete(metric.id);
            }
          });
        updateExportControls(state);
      });
    });
    state.page.querySelectorAll("[data-export-action]").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.exportAction === "select-all") {
          state.exportSelected = new Set(
            state.metrics.filter((metric) => metric.is_exportable).map((metric) => metric.id),
          );
        } else if (button.dataset.exportAction === "clear-all") {
          state.exportSelected = new Set();
        }
        updateExportControls(state);
      });
    });
    state.page.querySelectorAll("[data-metric-export]").forEach((button) => {
      button.addEventListener("click", () => {
        const metric = state.metricsById.get(button.dataset.metricExport);
        if (metric && state.data) {
          downloadMetric(state, metric);
        }
      });
    });
    const download = state.page.querySelector("[data-export-download]");
    if (download) {
      download.addEventListener("click", () => downloadSelected(state));
    }
    updateExportControls(state);
  }

  function updateRangeSummary(state) {
    const summary = state.page.querySelector("[data-range-summary]");
    if (!summary) {
      return;
    }
    if (state.activeRange === "ALL") {
      summary.textContent = "Showing all time data";
      return;
    }
    const labels = {
      "7D": "Showing the last 7 days",
      "30D": "Showing the last 30 days",
      "90D": "Showing the last 90 days",
      "1Y": "Showing the last 365 days",
      YTD: "Showing year to date",
    };
    summary.textContent = labels[state.activeRange] || `Showing ${state.activeRange}`;
  }

  function updateRangeButtons(state) {
    state.page.querySelectorAll("[data-studio-range]").forEach((button) => {
      const active = button.dataset.studioRange === state.activeRange;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    updateRangeSummary(state);
  }

  function metricUsesRange(metric) {
    return Boolean(
      metric.date_column
      || metric.period_key_column
      || (metric.sparkline_data_source && metric.sparkline_column)
      || [
        "recent_referral_deposits",
        "recent_etherfi_activity",
        "wallet_investigation",
      ].includes(metric.intelligence_component)
    );
  }

  function setRange(state, range) {
    if (!RANGE_OPTIONS.includes(range) || state.activeRange === range) {
      return;
    }
    state.activeRange = range;
    persistDashboardValue(state.rangeStorageKey, range);
    updateStudioUrlParameter("period", range);
    state.metrics.forEach((metric) => {
      if (metricUsesRange(metric)) {
        state.dirty.add(metric.id);
        const tableState = state.tables.get(metric.id);
        if (tableState) {
          tableState.page = 0;
        }
      }
    });
    updateRangeButtons(state);
    renderVisibleMetrics(state);
  }

  function findReferenceDate(state) {
    let latest = null;
    state.metrics.forEach((metric) => {
      const source = sourceForMetric(state, metric);
      if (Array.isArray(source) && metric.date_column) {
        const candidate = latestDate(source, metric.date_column);
        if (candidate && (!latest || candidate > latest)) {
          latest = candidate;
        }
      }
      if (
        metric.intelligence_component
        && source
        && typeof source === "object"
        && !Array.isArray(source)
      ) {
        const candidates = [
          latestDate(intelligenceWallets(source), "source_day"),
          latestDate(
            intelligenceGlobalCollection(source, ["referral_deposits", "deposits"]),
            "block_time",
          ),
          latestDate(
            intelligenceGlobalCollection(source, ["activity", "activities"]),
            "block_time",
          ),
        ].filter(Boolean);
        candidates.forEach((candidate) => {
          if (!latest || candidate > latest) {
            latest = candidate;
          }
        });
      }
      if (metric.sparkline_data_source) {
        const sparkline = sourceForMetric(state, metric, metric.sparkline_data_source);
        if (Array.isArray(sparkline) && sparkline.length) {
          const dateColumn = metric.sparkline_date_column
            || Object.keys(sparkline[0]).find((column) => /^(day|date|timestamp)$/i.test(column));
          const candidate = latestDate(sparkline, dateColumn);
          if (candidate && (!latest || candidate > latest)) {
            latest = candidate;
          }
        }
      }
    });
    return latest;
  }

  function bindRanges(state) {
    state.page.querySelectorAll("[data-studio-range]").forEach((button) => {
      button.addEventListener("click", () => setRange(state, button.dataset.studioRange));
    });
    updateRangeButtons(state);
  }

  function chartStyleMetricId(button) {
    if (button.dataset.chartStyleFor) {
      return button.dataset.chartStyleFor;
    }
    const card = button.closest("[data-studio-metric-id]");
    return card ? card.dataset.studioMetricId : "";
  }

  function updateChartStyleButtons(state, metric) {
    state.page.querySelectorAll("[data-chart-style]").forEach((button) => {
      if (chartStyleMetricId(button) !== metric.id) {
        return;
      }
      const active = button.dataset.chartStyle === chartStyleForMetric(state, metric);
      button.classList.toggle("active", active);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function bindChartStyles(state) {
    state.metrics
      .filter((metric) => metric.visualization_type === "line")
      .forEach((metric) => {
        state.chartStyles.set(metric.id, defaultChartStyle(metric));
        updateChartStyleButtons(state, metric);
      });
    state.page.querySelectorAll("[data-chart-style]").forEach((button) => {
      button.addEventListener("click", () => {
        const metric = state.metricsById.get(chartStyleMetricId(button));
        const style = button.dataset.chartStyle;
        if (
          !metric
          || metric.visualization_type !== "line"
          || !allowedChartStyles(metric).includes(style)
        ) {
          return;
        }
        state.chartStyles.set(metric.id, style);
        updateChartStyleButtons(state, metric);
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      });
    });
  }

  function updateMomentumControlState(state, metric) {
    const selection = state.momentumSelections.get(metric.id);
    if (!selection) {
      return;
    }
    state.page.querySelectorAll(
      `[data-momentum-granularity-for="${metric.id}"]`,
    ).forEach((button) => {
      const active = button.dataset.momentumGranularity === selection.granularity;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const select = state.page.querySelector(`[data-momentum-filter="${metric.id}"]`);
    if (select) {
      select.value = selection.filter;
    }
  }

  function bindMomentumControls(state) {
    state.metrics.filter((metric) => metric.momentum_chart).forEach((metric) => {
      state.momentumSelections.set(metric.id, {
        granularity: metric.momentum_chart.default_granularity,
        filter: "all",
      });
      updateMomentumControlState(state, metric);
    });
    state.page.querySelectorAll("[data-momentum-granularity]").forEach((button) => {
      button.addEventListener("click", () => {
        const metric = state.metricsById.get(button.dataset.momentumGranularityFor);
        const granularity = button.dataset.momentumGranularity;
        const selection = metric && state.momentumSelections.get(metric.id);
        if (!metric || !selection || !["daily", "weekly"].includes(granularity)) {
          return;
        }
        selection.granularity = granularity;
        updateMomentumControlState(state, metric);
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      });
    });
    state.page.querySelectorAll("[data-momentum-filter]").forEach((select) => {
      select.addEventListener("change", () => {
        const metric = state.metricsById.get(select.dataset.momentumFilter);
        const selection = metric && state.momentumSelections.get(metric.id);
        if (!metric || !selection) {
          return;
        }
        selection.filter = select.value || "all";
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      });
    });
  }

  function updateGrowthControlState(state, metric) {
    const selection = state.growthSelections.get(metric.id);
    if (!selection) {
      return;
    }
    state.page.querySelectorAll(
      `[data-growth-granularity-for="${metric.id}"]`,
    ).forEach((control) => {
      if (control.tagName === "SELECT") {
        control.value = selection.granularity;
        return;
      }
      const active = control.dataset.growthGranularity === selection.granularity;
      control.classList.toggle("is-active", active);
      control.setAttribute("aria-pressed", String(active));
    });
    state.page.querySelectorAll(`[data-growth-view-for="${metric.id}"]`).forEach((control) => {
      if (control.tagName === "SELECT") {
        control.value = selection.view;
        return;
      }
      const active = control.dataset.growthView === selection.view;
      control.classList.toggle("is-active", active);
      control.setAttribute("aria-pressed", String(active));
    });
  }

  function bindGrowthControls(state) {
    state.metrics.filter((metric) => metric.growth_chart).forEach((metric) => {
      const config = metric.growth_chart;
      const firstView = growthChartViews(metric)[0];
      state.growthSelections.set(metric.id, {
        granularity: config.default_granularity || "weekly",
        view: config.default_view || firstView && firstView.id || "all",
      });
      updateGrowthControlState(state, metric);
    });
    state.page.querySelectorAll("[data-growth-granularity-for]").forEach((control) => {
      const update = () => {
        const metric = state.metricsById.get(control.dataset.growthGranularityFor);
        const selection = metric && state.growthSelections.get(metric.id);
        const granularity = control.tagName === "SELECT"
          ? control.value
          : control.dataset.growthGranularity;
        const available = metric && Array.isArray(metric.growth_chart.available_granularities)
          ? metric.growth_chart.available_granularities
          : ["daily", "weekly"];
        if (!metric || !selection || !available.includes(granularity)) {
          return;
        }
        selection.granularity = granularity;
        updateGrowthControlState(state, metric);
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      };
      control.addEventListener(control.tagName === "SELECT" ? "change" : "click", update);
    });
    state.page.querySelectorAll("[data-growth-view-for]").forEach((control) => {
      const update = () => {
        const metric = state.metricsById.get(control.dataset.growthViewFor);
        const selection = metric && state.growthSelections.get(metric.id);
        const view = control.tagName === "SELECT" ? control.value : control.dataset.growthView;
        if (
          !metric
          || !selection
          || !growthChartViews(metric).some((candidate) => candidate.id === view)
        ) {
          return;
        }
        selection.view = view;
        updateGrowthControlState(state, metric);
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      };
      control.addEventListener(control.tagName === "SELECT" ? "change" : "click", update);
    });
  }

  function sectionNavId(value) {
    return String(value || "").replace(/^#?(?:studio-section-)?/, "");
  }

  function setActiveSectionNav(state, sectionId) {
    const normalized = sectionNavId(sectionId);
    state.page.querySelectorAll("[data-section-nav-target]").forEach((control) => {
      const active = sectionNavId(control.dataset.sectionNavTarget) === normalized;
      control.classList.toggle("is-active", active);
      if (active) {
        control.setAttribute("aria-current", "location");
      } else {
        control.removeAttribute("aria-current");
      }
    });
    return normalized;
  }

  function updateSectionNavigation(state) {
    const controls = [...state.page.querySelectorAll("[data-section-nav-target]")];
    if (!controls.length) {
      return;
    }
    controls.forEach((control) => {
      const id = sectionNavId(control.dataset.sectionNavTarget);
      const section = state.page.querySelector(`[data-studio-section="${id}"]`);
      control.hidden = !section || section.hidden;
    });
    const active = controls.find((control) => (
      !control.hidden && control.getAttribute("aria-current") === "location"
    ));
    if (!active) {
      const firstVisible = controls.find((control) => !control.hidden);
      if (firstVisible) {
        setActiveSectionNav(state, firstVisible.dataset.sectionNavTarget);
      }
    }
  }

  function bindSectionNavigation(state) {
    const controls = [...state.page.querySelectorAll("[data-section-nav-target]")];
    if (!controls.length) {
      return;
    }
    controls.forEach((control) => {
      control.addEventListener("click", (event) => {
        const sectionId = sectionNavId(control.dataset.sectionNavTarget);
        const section = state.page.querySelector(`[data-studio-section="${sectionId}"]`);
        if (!section) {
          return;
        }
        event.preventDefault();
        const reduceMotion = root && typeof root.matchMedia === "function"
          && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
        section.scrollIntoView({
          behavior: reduceMotion ? "auto" : "smooth",
          block: "start",
        });
        setActiveSectionNav(state, sectionId);
      });
    });
    updateSectionNavigation(state);
    if (!root || typeof root.IntersectionObserver !== "function") {
      return;
    }
    state.sectionObserver = new root.IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting && !entry.target.hidden)
        .sort((left, right) => (
          Math.abs(left.boundingClientRect.top) - Math.abs(right.boundingClientRect.top)
        ));
      if (visible.length) {
        setActiveSectionNav(state, visible[0].target.dataset.studioSection);
      }
    }, {
      rootMargin: "-15% 0px -70% 0px",
      threshold: [0, 0.01, 0.25],
    });
    state.page.querySelectorAll("[data-studio-section]").forEach((section) => (
      state.sectionObserver.observe(section)
    ));
  }

  function bindTopN(state) {
    state.page.querySelectorAll("[data-top-n-for]").forEach((select) => {
      const id = select.dataset.topNFor;
      const value = Number(select.value);
      if (Number.isFinite(value) && value > 0) {
        state.topN.set(id, value);
      }
      select.addEventListener("change", () => {
        const next = Number(select.value);
        if (!Number.isFinite(next) || next < 1) {
          return;
        }
        state.topN.set(id, next);
        state.dirty.add(id);
        const metric = state.metricsById.get(id);
        if (metric) {
          renderMetric(state, metric);
        }
      });
    });
  }

  function panelToggleModel(dataset, side) {
    if (!dataset || !["left", "right"].includes(side)) {
      return null;
    }
    const current = {
      leftCollapsed: String(dataset.leftCollapsed) === "true",
      rightCollapsed: String(dataset.rightCollapsed) === "true",
    };
    const key = `${side}Collapsed`;
    const next = {
      ...current,
      [key]: !current[key],
    };
    const collapsed = next[key];
    const panelName = side === "left"
      ? "dashboard navigation"
      : "metrics and downloads";
    return {
      ...next,
      collapsed,
      ariaExpanded: String(!collapsed),
      ariaLabel: `${collapsed ? "Expand" : "Collapse"} ${panelName} panel`,
      icon: side === "left"
        ? (collapsed ? "→" : "←")
        : (collapsed ? "←" : "→"),
    };
  }

  function bindPanels(state) {
    state.page.querySelectorAll("[data-panel-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const side = button.dataset.panelToggle;
        const panel = state.page.querySelector(`[data-studio-panel="${side}"]`);
        const model = panelToggleModel(state.workspace.dataset, side);
        if (!model) {
          return;
        }
        state.workspace.dataset.leftCollapsed = String(model.leftCollapsed);
        state.workspace.dataset.rightCollapsed = String(model.rightCollapsed);
        if (panel) {
          panel.classList.toggle("is-collapsed", model.collapsed);
        }
        button.setAttribute("aria-expanded", model.ariaExpanded);
        button.setAttribute("aria-label", model.ariaLabel);
        const icon = button.querySelector("[aria-hidden]");
        if (icon) {
          icon.textContent = model.icon;
        }
        scheduleChartResize(state);
      });
    });
  }

  function navigateToSelection(select) {
    const destination = select && select.value;
    if (!destination || !root || !root.location) {
      return false;
    }
    if (typeof root.location.assign === "function") {
      root.location.assign(destination);
    } else {
      root.location.href = destination;
    }
    return true;
  }

  function bindDashboardSelector(state) {
    state.page.querySelectorAll("[data-studio-dashboard-select]").forEach((select) => {
      select.addEventListener("change", () => navigateToSelection(select));
    });
  }

  function markAllMetricsError(state, title, message) {
    state.metrics.forEach((metric) => {
      renderMetricState(state, metric, "error", title, message);
      state.rendered.add(metric.id);
    });
  }

  function handleFlowBreakpoint(state) {
    state.metrics
      .filter((metric) => metric.visualization_type === "sankey")
      .forEach((metric) => {
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      });
  }

  function handleThemeChange(state) {
    state.metrics
      .filter((metric) => ["line", "bar", "sankey"].includes(metric.visualization_type))
      .forEach((metric) => {
        state.dirty.add(metric.id);
        renderMetric(state, metric);
      });
  }

  function bindResponsiveBehavior(state) {
    if (root && typeof root.matchMedia === "function") {
      state.mobileQuery = root.matchMedia(`(max-width: ${STUDIO_MOBILE_BREAKPOINT}px)`);
      const listener = () => handleFlowBreakpoint(state);
      if (typeof state.mobileQuery.addEventListener === "function") {
        state.mobileQuery.addEventListener("change", listener);
      } else if (typeof state.mobileQuery.addListener === "function") {
        state.mobileQuery.addListener(listener);
      }
    }
    if (root && typeof root.addEventListener === "function") {
      root.addEventListener("resize", () => scheduleChartResize(state), { passive: true });
    }
    if (root && typeof root.ResizeObserver === "function") {
      state.resizeObserver = new root.ResizeObserver(() => scheduleChartResize(state));
      state.resizeObserver.observe(state.workspace);
    }
    if (
      root
      && typeof root.MutationObserver === "function"
      && state.page.ownerDocument
      && state.page.ownerDocument.documentElement
    ) {
      state.themeObserver = new root.MutationObserver((records) => {
        if (records.some((record) => record.attributeName === "data-theme")) {
          handleThemeChange(state);
        }
      });
      state.themeObserver.observe(state.page.ownerDocument.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
    }
  }

  function expectedColumnsBySource(metrics) {
    const expected = {};
    (Array.isArray(metrics) ? metrics : []).forEach((metric) => {
      const sourceName = metric && (metric.derived_data_source || metric.data_source);
      if (!metric || !sourceName) {
        return;
      }
      expected[sourceName] = uniqueColumns([
        ...(expected[sourceName] || []),
        ...requiredColumnsForMetric(metric),
      ]);
      if (metric.sparkline_data_source && metric.sparkline_column) {
        expected[metric.sparkline_data_source] = uniqueColumns([
          ...(expected[metric.sparkline_data_source] || []),
          metric.sparkline_column,
          metric.sparkline_date_column,
        ]);
      }
    });
    return expected;
  }

  function fetchJsonOnce(cache, fetcher, url) {
    if (cache.has(url)) {
      return cache.get(url);
    }
    const request = Promise.resolve()
      .then(() => fetcher(url, { credentials: "same-origin", cache: "no-store" }))
      .then((response) => {
        if (!response || response.ok === false) {
          const status = response && response.status;
          const error = new Error(
            status ? `Data request returned ${status}.` : "Data request failed.",
          );
          error.code = "unavailable";
          throw error;
        }
        if (typeof response.json !== "function") {
          const error = new Error("Data response did not provide JSON.");
          error.code = "malformed";
          throw error;
        }
        return Promise.resolve(response.json()).catch((cause) => {
          const error = new Error(
            cause && cause.message
              ? `Data response is not valid JSON: ${cause.message}`
              : "Data response is not valid JSON.",
          );
          error.code = "malformed";
          throw error;
        });
      });
    cache.set(url, request);
    return request;
  }

  function latestTimestamp(values) {
    let selected = "";
    let selectedTime = -Infinity;
    (Array.isArray(values) ? values : []).forEach((value) => {
      const parsed = parseDate(value);
      if (parsed && parsed.getTime() > selectedTime) {
        selected = String(value);
        selectedTime = parsed.getTime();
      }
    });
    return selected;
  }

  function oldestTimestamp(values) {
    let selected = "";
    let selectedTime = Infinity;
    (Array.isArray(values) ? values : []).forEach((value) => {
      const parsed = parseDate(value);
      if (parsed && parsed.getTime() < selectedTime) {
        selected = String(value);
        selectedTime = parsed.getTime();
      }
    });
    return selected;
  }

  function aggregateFreshnessStatus(sourceMetadata) {
    const priority = { current: 0, delayed: 1, stale: 2 };
    let selected = "current";
    let selectedPriority = 0;
    (Array.isArray(sourceMetadata) ? sourceMetadata : []).forEach((metadata) => {
      const status = String(
        (metadata && metadata.freshness_status)
        || "current",
      ).toLocaleLowerCase("en");
      const statusPriority = Object.prototype.hasOwnProperty.call(priority, status)
        ? priority[status]
        : 0;
      if (statusPriority > selectedPriority) {
        selected = status;
        selectedPriority = statusPriority;
      }
    });
    return selected;
  }

  function aggregateResultStatus(sourceMetadata) {
    const statuses = (Array.isArray(sourceMetadata) ? sourceMetadata : [])
      .map((metadata) => String(
        (metadata && metadata.result_status)
        || (metadata && metadata.status)
        || "failed",
      ).toLocaleLowerCase("en"));
    if (!statuses.length || statuses.every((status) => status === "failed")) {
      return "failed";
    }
    if (statuses.some((status) => status === "failed")) {
      return "partial";
    }
    if (statuses.every((status) => status === "empty")) {
      return "empty";
    }
    return "success";
  }

  function applyActiveSnapshotContext(normalized, manifest, refreshStatus) {
    const result = normalized || sourceFailure(
      "unavailable",
      "The configured data source is unavailable.",
      "Refresh the Studio snapshot and try again.",
      {},
    );
    const hasRows = isUsableSource(result.data);
    const usingPrevious = Boolean(
      refreshStatus
      && refreshStatus.using_previous
      && ["failed", "partial"].includes(refreshStatus.latest_attempt_status),
    );
    const sourceQueryId = Number(result.meta && result.meta.query_id);
    const reusedQueryIds = new Set([
      ...((manifest && Array.isArray(manifest.reused_query_ids))
        ? manifest.reused_query_ids
        : []),
      ...((refreshStatus
        && refreshStatus.latest_failure
        && Array.isArray(refreshStatus.latest_failure.failed_query_ids))
        ? refreshStatus.latest_failure.failed_query_ids
        : []),
    ].map(Number));
    const sourceUsingPrevious = usingPrevious && (
      refreshStatus.latest_attempt_status === "failed"
      || (Number.isSafeInteger(sourceQueryId) && reusedQueryIds.has(sourceQueryId))
    );
    result.meta = {
      ...(result.meta || {}),
      snapshot_id: (manifest && manifest.snapshot_id)
        || (result.meta && result.meta.snapshot_id)
        || "",
      snapshot_state: hasRows
        ? (sourceUsingPrevious ? "previous" : "current")
        : "unavailable",
      display_updated_at: (result.meta && result.meta.display_updated_at)
        || (result.meta && result.meta.data_updated_at)
        || (result.meta && result.meta.execution_finished_at)
        || (manifest && manifest.display_updated_at)
        || "",
      using_previous: hasRows && sourceUsingPrevious,
      latest_attempt_status: refreshStatus
        ? refreshStatus.latest_attempt_status
        : "",
      last_checked_at: refreshStatus ? refreshStatus.last_checked_at : "",
    };
    return result;
  }

  function assembleStudioData(
    config,
    results,
    manifest,
    manifestError,
    refreshStatus,
    refreshStatusError,
  ) {
    const datasets = {};
    const sourceMeta = {};
    let dashboardMeta = {};
    results.forEach((result) => {
      datasets[result.name] = result.normalized.data;
      sourceMeta[result.name] = result.normalized.meta;
      if (
        result.normalized.dashboardMeta
        && !Object.keys(dashboardMeta).length
      ) {
        dashboardMeta = { ...result.normalized.dashboardMeta };
      }
    });
    const sourceGeneratedAt = latestTimestamp(
      Object.values(sourceMeta).map((metadata) => metadata.generated_at),
    );
    const sourceExecutionFinishedAt = oldestTimestamp(
      Object.values(sourceMeta).map(
        (metadata) => metadata.execution_finished_at,
      ),
    );
    const sourceDataUpdatedAt = oldestTimestamp(
      Object.values(sourceMeta).map(
        (metadata) => metadata.data_updated_at
          || metadata.execution_finished_at
          || metadata.generated_at,
      ),
    );
    const sourceDisplayUpdatedAt = oldestTimestamp(
      Object.values(sourceMeta).map(
        (metadata) => metadata.display_updated_at
          || metadata.data_updated_at
          || metadata.execution_finished_at
          || metadata.generated_at,
      ),
    );
    const freshnessStatus = aggregateFreshnessStatus(Object.values(sourceMeta));
    const resultStatus = aggregateResultStatus(Object.values(sourceMeta));
    const configuredDashboard = config.dashboard || {};
    const generatedAt = (manifest && manifest.generated_at)
      || dashboardMeta.generated_at
      || dashboardMeta.last_refreshed
      || configuredDashboard.generated_at
      || configuredDashboard.last_refreshed
      || sourceGeneratedAt
      || "";
    const displayUpdatedAt = sourceDisplayUpdatedAt
      || dashboardMeta.display_updated_at
      || (manifest && manifest.display_updated_at)
      || generatedAt;
    const dashboardRefreshedAt = (
      manifest
      && (
        manifest.dashboard_refreshed_at
        || manifest.last_successful_fetch_at
        || manifest.generated_at
      )
    )
      || dashboardMeta.dashboard_refreshed_at
      || generatedAt;
    const dataUpdatedAt = sourceDataUpdatedAt
      || dashboardMeta.data_updated_at
      || (manifest && manifest.data_updated_at)
      || sourceExecutionFinishedAt
      || displayUpdatedAt;
    const usingPrevious = Boolean(
      refreshStatus
      && refreshStatus.using_previous
      && ["failed", "partial"].includes(refreshStatus.latest_attempt_status),
    );
    const usableSourceCount = Object.values(datasets)
      .filter((dataset) => isUsableSource(dataset)).length;
    const manifestStatus = manifestError
      ? (manifestError.code === "malformed" ? "malformed" : "unavailable")
      : (manifest ? "ready" : "");
    const refreshStatusState = refreshStatusError
      ? (refreshStatusError.code === "malformed" ? "malformed" : "unavailable")
      : (refreshStatus ? "ready" : "");
    return {
      meta: {
        ...dashboardMeta,
        dashboard_id: dashboardMeta.dashboard_id || configuredDashboard.id || "",
        status: dashboardMeta.status
          || config.dataMode
          || configuredDashboard.status
          || "",
        result_status: resultStatus,
        freshness_status: freshnessStatus,
        snapshot_id: (manifest && manifest.snapshot_id) || "",
        snapshot_state: usableSourceCount
          ? (
            usingPrevious && refreshStatus.latest_attempt_status === "partial"
              ? "partial"
              : (usingPrevious ? "previous" : "current")
          )
          : "unavailable",
        using_previous: usingPrevious,
        generated_at: generatedAt,
        dashboard_refreshed_at: dashboardRefreshedAt,
        display_updated_at: displayUpdatedAt,
        data_updated_at: dataUpdatedAt,
        last_refreshed: dashboardMeta.last_refreshed || displayUpdatedAt,
        execution_finished_at: sourceExecutionFinishedAt,
        manifest_status: manifestStatus,
        manifest_error: manifestError
          ? String(manifestError.message || manifestError)
          : "",
        refresh_status_status: refreshStatusState,
        refresh_status_error: refreshStatusError
          ? String(refreshStatusError.message || refreshStatusError)
          : "",
        latest_attempt_status: refreshStatus
          ? refreshStatus.latest_attempt_status
          : "",
        last_checked_at: refreshStatus ? refreshStatus.last_checked_at : "",
        latest_failure: refreshStatus && refreshStatus.latest_failure
          ? { ...refreshStatus.latest_failure }
          : null,
      },
      datasets,
      sourceMeta,
      manifest: manifest || null,
      refreshStatus: refreshStatus || null,
    };
  }

  function normalizeFetchFailure(error, descriptor) {
    const metadata = normalizedSourceMetadata(descriptor, {});
    const code = error && error.code === "malformed"
      ? "malformed"
      : "unavailable";
    return sourceFailure(
      code,
      code === "malformed"
        ? "The generated data file is malformed."
        : "The generated data file is unavailable.",
      error && error.message
        ? error.message
        : "Refresh the Studio snapshot and try again.",
      metadata,
    );
  }

  function loadLegacyDashboardData(config, fetcher, cache, nowValue) {
    return fetchJsonOnce(cache, fetcher, config.dataUrl).then((payload) => {
      if (
        payload
        && payload.meta
        && payload.meta.dashboard_id
        && config.dashboard
        && payload.meta.dashboard_id !== config.dashboard.id
      ) {
        throw new Error("The generated data file belongs to another dashboard.");
      }
      const expected = expectedColumnsBySource(config.metrics);
      const sourceNames = Object.keys(expected);
      const results = sourceNames.map((name) => ({
        name,
        normalized: normalizeDemoBundle(
          payload,
          {
            kind: "demo_bundle",
            url: config.dataUrl,
            dataset: name,
            expectedColumns: expected[name],
          },
          name,
          nowValue,
        ),
      }));
      return assembleStudioData(config, results, null, null);
    });
  }

  function loadStudioSources(config, fetcher, nowValue) {
    if (!config || typeof config !== "object") {
      return Promise.reject(new Error("Studio data configuration is missing."));
    }
    if (typeof fetcher !== "function") {
      return Promise.reject(new Error("Studio data loading requires fetch."));
    }
    const cache = new Map();
    const configuredSources = config.dataSources
      && typeof config.dataSources === "object"
      && !Array.isArray(config.dataSources)
      ? config.dataSources
      : null;
    if (!configuredSources || !Object.keys(configuredSources).length) {
      if (!config.dataUrl) {
        return Promise.reject(new Error("Studio has no configured data sources."));
      }
      return loadLegacyDashboardData(config, fetcher, cache, nowValue);
    }

    const sourceEntries = Object.entries(configuredSources);
    const generatedEntries = sourceEntries.filter(([, descriptor]) => (
      descriptor && descriptor.kind === "generated_query"
    ));
    const derivedEntries = sourceEntries.filter(([, descriptor]) => (
      descriptor && descriptor.kind === "generated_derived"
    ));
    const directEntries = sourceEntries.filter(([, descriptor]) => (
      !descriptor || !["generated_query", "generated_derived"].includes(descriptor.kind)
    ));

    const manifestTask = generatedEntries.length || derivedEntries.length
      ? (
        config.manifestUrl
          ? fetchJsonOnce(cache, fetcher, config.manifestUrl)
            .then((payload) => {
              try {
                return { value: normalizeManifest(payload), error: null };
              } catch (error) {
                error.code = "malformed";
                return { value: null, error };
              }
            })
            .catch((error) => ({ value: null, error }))
          : Promise.resolve({
            value: null,
            error: Object.assign(
              new Error("The generated-data manifest URL is missing."),
              { code: "malformed" },
            ),
          })
      )
      : Promise.resolve({ value: null, error: null });

    const refreshStatusUrl = (generatedEntries.length || derivedEntries.length) && config.manifestUrl
      ? (
        config.refreshStatusUrl
        || siblingDataUrl(config.manifestUrl, "refresh_status.json")
      )
      : "";
    const refreshStatusTask = refreshStatusUrl
      ? fetchJsonOnce(cache, fetcher, refreshStatusUrl)
        .then((payload) => {
          try {
            return { value: normalizeRefreshStatus(payload), error: null };
          } catch (error) {
            error.code = "malformed";
            return { value: null, error };
          }
        })
        .catch((error) => ({ value: null, error }))
      : Promise.resolve({ value: null, error: null });

    const directTasks = directEntries.map(([name, descriptorValue]) => {
      const descriptor = descriptorValue || {};
      if (descriptor.kind !== "demo_bundle") {
        return Promise.resolve({
          name,
          normalized: sourceFailure(
            "malformed",
            "The configured data-source kind is unsupported.",
            `Studio cannot load “${descriptor.kind || "unknown"}”.`,
            normalizedSourceMetadata(descriptor, {}),
          ),
        });
      }
      if (!descriptor.url) {
        return Promise.resolve({
          name,
          normalized: sourceFailure(
            "malformed",
            "The data source has no configured URL.",
            "Update the Studio data-source configuration.",
            normalizedSourceMetadata(descriptor, {}),
          ),
        });
      }
      return fetchJsonOnce(cache, fetcher, descriptor.url)
        .then((payload) => ({
          name,
          normalized: normalizeDemoBundle(
            payload,
            descriptor,
            name,
            nowValue,
          ),
        }))
        .catch((error) => ({
          name,
          normalized: normalizeFetchFailure(error, descriptor),
        }));
    });

    return Promise.all([
      manifestTask,
      refreshStatusTask,
      Promise.all(directTasks),
    ]).then(([manifestResult, refreshStatusResult, directResults]) => {
      const manifest = manifestResult.value;
      let refreshStatus = refreshStatusResult.value;
      let refreshStatusError = refreshStatusResult.error;
      if (
        manifest
        && refreshStatus
        && refreshStatus.current_snapshot_id !== manifest.snapshot_id
      ) {
        refreshStatus = null;
        refreshStatusError = Object.assign(
          new Error("The Studio refresh status does not match the active snapshot."),
          { code: "malformed" },
        );
      }
      const generatedTasks = generatedEntries.map(([name, descriptorValue]) => {
        const descriptor = descriptorValue || {};
        if (manifestResult.error || !manifest) {
          const error = manifestResult.error || Object.assign(
            new Error("The generated-data manifest is unavailable."),
            { code: "unavailable" },
          );
          const manifestCode = error.code === "unavailable"
            ? "unavailable"
            : "malformed";
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              manifestCode,
              manifestCode === "unavailable"
                ? "The generated-data manifest is unavailable."
                : "The generated-data manifest is malformed.",
              error.message || "Studio could not verify this query file.",
              normalizedSourceMetadata(descriptor, {}),
            ),
          });
        }
        const manifestEntry = manifest.queries.find((entry) => (
          Number(entry.query_id) === Number(descriptor.queryId)
        ));
        if (!manifestEntry) {
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              "malformed",
              "The generated query is missing from the manifest.",
              `Query ${descriptor.queryId} has no manifest entry.`,
              normalizedSourceMetadata(descriptor, {}),
            ),
          });
        }
        if (
          descriptor.dataFile
          && String(descriptor.dataFile) !== String(manifestEntry.data_file)
        ) {
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              "malformed",
              "The generated query configuration does not match its manifest.",
              "The configured and active query file names differ.",
              normalizedSourceMetadata(descriptor, manifestEntry),
            ),
          });
        }
        let queryUrl;
        try {
          queryUrl = manifestResultUrl(config.manifestUrl, manifestEntry);
        } catch (error) {
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              "malformed",
              "The generated query path is invalid.",
              error.message,
              normalizedSourceMetadata(descriptor, manifestEntry),
            ),
          });
        }
        return fetchJsonOnce(cache, fetcher, queryUrl)
          .then((payload) => ({
            name,
            normalized: applyActiveSnapshotContext(
              normalizeGeneratedQuery(
                payload,
                descriptor,
                nowValue,
                manifestEntry,
              ),
              manifest,
              refreshStatus,
            ),
          }))
          .catch((error) => ({
            name,
            normalized: applyActiveSnapshotContext(
              normalizeFetchFailure(error, descriptor),
              manifest,
              refreshStatus,
            ),
          }));
      });
      const derivedTasks = derivedEntries.map(([name, descriptorValue]) => {
        const descriptor = descriptorValue || {};
        if (manifestResult.error || !manifest) {
          const error = manifestResult.error || Object.assign(
            new Error("The generated-data manifest is unavailable."),
            { code: "unavailable" },
          );
          const code = error.code === "unavailable" ? "unavailable" : "malformed";
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              code,
              code === "unavailable"
                ? "The generated-data manifest is unavailable."
                : "The generated-data manifest is malformed.",
              error.message || "Studio could not verify this derived artifact.",
              normalizedSourceMetadata(descriptor, {}),
            ),
          });
        }
        const artifactId = derivedArtifactId(descriptor, name);
        const manifestEntry = (Array.isArray(manifest.artifacts) ? manifest.artifacts : [])
          .find((entry) => (
            String(entry.artifact_id || entry.id || entry.data_source || "") === artifactId
          ));
        if (!manifestEntry) {
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              "malformed",
              "The generated artifact is missing from the manifest.",
              `Artifact ${artifactId || name} has no manifest entry.`,
              normalizedSourceMetadata(descriptor, {}),
            ),
          });
        }
        const descriptorFile = descriptor.dataFile || descriptor.data_file;
        if (descriptorFile && String(descriptorFile) !== String(manifestEntry.data_file)) {
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              "malformed",
              "The generated artifact configuration does not match its manifest.",
              "The configured and active artifact file names differ.",
              normalizedSourceMetadata(descriptor, manifestEntry),
            ),
          });
        }
        let artifactUrl;
        try {
          artifactUrl = descriptor.url
            || manifestArtifactUrl(config.manifestUrl, manifestEntry);
        } catch (error) {
          return Promise.resolve({
            name,
            normalized: sourceFailure(
              "malformed",
              "The generated artifact path is invalid.",
              error.message,
              normalizedSourceMetadata(descriptor, manifestEntry),
            ),
          });
        }
        return fetchJsonOnce(cache, fetcher, artifactUrl)
          .then((payload) => ({
            name,
            normalized: applyActiveSnapshotContext(
              normalizeGeneratedDerived(
                payload,
                descriptor,
                name,
                nowValue,
                manifestEntry,
              ),
              manifest,
              refreshStatus,
            ),
          }))
          .catch((error) => ({
            name,
            normalized: applyActiveSnapshotContext(
              normalizeFetchFailure(error, descriptor),
              manifest,
              refreshStatus,
            ),
          }));
      });
      return Promise.all([...generatedTasks, ...derivedTasks]).then((generatedResults) => {
        const resultsByName = new Map(
          [...directResults, ...generatedResults]
            .map((result) => [result.name, result]),
        );
        const results = sourceEntries.map(([name]) => resultsByName.get(name));
        return assembleStudioData(
          config,
          results,
          manifest,
          manifestResult.error,
          refreshStatus,
          refreshStatusError,
        );
      });
    });
  }

  function updateDashboardTimestamp(state) {
    const timestamp = state
      && state.data
      && state.data.meta
      && (
        state.data.meta.dashboard_refreshed_at
        || state.data.meta.display_updated_at
        || state.data.meta.data_updated_at
        || state.data.meta.generated_at
        || state.data.meta.last_refreshed
      );
    if (!timestamp || !state.page || typeof state.page.querySelector !== "function") {
      return;
    }
    const time = state.page.querySelector("[data-studio-last-updated]");
    if (!time) {
      return;
    }
    time.dateTime = String(timestamp);
    time.setAttribute("datetime", String(timestamp));
    time.textContent = utcTimestampLabel(timestamp);
  }

  function parseConfig(page) {
    const script = page.querySelector(CONFIG_SELECTOR);
    if (!script) {
      throw new Error("Studio configuration is missing.");
    }
    const config = JSON.parse(script.textContent || "{}");
    if (
      !config.dashboard
      || !config.dashboard.id
      || !Array.isArray(config.metrics)
      || (
        !config.dataUrl
        && (
          !config.dataSources
          || typeof config.dataSources !== "object"
          || Array.isArray(config.dataSources)
          || !Object.keys(config.dataSources).length
        )
      )
    ) {
      throw new Error("Studio configuration is incomplete.");
    }
    return config;
  }

  function loadDashboardData(state) {
    if (!root || typeof root.fetch !== "function") {
      markAllMetricsError(
        state,
        "Generated dashboard data could not be loaded.",
        "This browser does not provide the required fetch API.",
      );
      return Promise.resolve(null);
    }
    return loadStudioSources(
      state.config,
      root.fetch.bind(root),
      new Date(),
    )
      .then((payload) => {
        state.data = payload;
        state.referenceDate = findReferenceDate(state);
        state.metrics.forEach((metric) => state.dirty.add(metric.id));
        updateDashboardTimestamp(state);
        updateExportControls(state);
        updateRangeButtons(state);
        renderVisibleMetrics(state);
        return payload;
      })
      .catch((error) => {
        markAllMetricsError(
          state,
          "Generated dashboard data could not be loaded.",
          error && error.message ? error.message : "Reload the page to retry.",
        );
        setExportFeedback(state, "Dashboard data is unavailable for export.", "error");
        return null;
      });
  }

  function mount(scope) {
    const page = scope && scope.querySelector
      ? scope.querySelector(DASHBOARD_SELECTOR)
      : null;
    if (!page || page.dataset.studioMounted === "true") {
      return null;
    }
    let config;
    try {
      config = parseConfig(page);
    } catch (error) {
      const main = page.querySelector("[data-studio-dashboard-main]") || page;
      const warning = createElement(
        scope,
        "div",
        "studio-metric-state studio-error-state",
      );
      warning.append(
        createElement(scope, "strong", "", "Studio could not start."),
        createElement(scope, "p", "", error.message),
      );
      main.prepend(warning);
      page.dataset.studioMounted = "error";
      return null;
    }
    const metrics = config.metrics.slice().sort((left, right) => (
      Number(left.display_order || 0) - Number(right.display_order || 0)
    ));
    const rangeStorageKey = dashboardStateStorageKey("period", config.dashboard.id);
    const walletStorageKey = dashboardStateStorageKey("wallet", config.dashboard.id);
    const recentWalletsKey = dashboardStateStorageKey(
      "recent-wallets",
      config.dashboard.id,
    );
    const explicitWallet = studioUrlParameter("wallet");
    const restoredWallet = explicitWallet || storedDashboardValue(walletStorageKey);
    const state = {
      page,
      config,
      metrics,
      metricsById: new Map(metrics.map((metric) => [metric.id, metric])),
      workspace: page.querySelector("[data-studio-workspace]") || page,
      data: null,
      referenceDate: null,
      activeRange: restoredDashboardRange(config, rangeStorageKey),
      visible: new Set(),
      exportSelected: new Set(
        metrics.filter((metric) => metric.is_exportable).map((metric) => metric.id),
      ),
      charts: new Map(),
      rendered: new Set(),
      dirty: new Set(),
      tables: new Map(),
      topN: new Map(),
      chartStyles: new Map(),
      momentumSelections: new Map(),
      growthSelections: new Map(),
      intelligenceMeasures: new Map(),
      selectedWallet: normalizeWalletAddress(restoredWallet),
      walletInputError: explicitWallet && !normalizeWalletAddress(explicitWallet)
        ? "The wallet address in this URL is invalid."
        : "",
      recentWallets: restoredRecentWallets(recentWalletsKey),
      rangeStorageKey,
      walletStorageKey,
      recentWalletsKey,
      relativeAgeTimer: null,
      resizeTimer: null,
      resizeObserver: null,
      themeObserver: null,
      sectionObserver: null,
      mobileQuery: null,
      counterWarnings: new Set(),
      visibilityKey: visibilityStorageKey(config.dashboard.id, metrics),
      visibilityDisclosureKey: visibilityDisclosureStorageKey(
        config.dashboard.id,
        metrics,
      ),
      expandedVisibilitySections: new Set(),
    };
    metrics.forEach((metric) => {
      const card = page.querySelector(`[data-studio-metric-id="${metric.id}"]`);
      if (card) {
        if (metric.intelligence_component) {
          card.dataset.intelligenceComponent = metric.intelligence_component;
        }
        card.classList.toggle(
          "studio-counter-compact",
          metric.visualization_type === "counter" && Boolean(metric.compact_counter),
        );
        card.classList.toggle("studio-growth-card", Boolean(metric.growth_chart));
      }
    });
    state.visible = restoredVisibility(state);
    state.expandedVisibilitySections = restoredVisibilityDisclosures(state);
    bindDashboardSelector(state);
    bindSectionNavigation(state);
    bindPanels(state);
    bindVisibility(state);
    bindExports(state);
    bindRanges(state);
    bindChartStyles(state);
    bindMomentumControls(state);
    bindGrowthControls(state);
    bindTopN(state);
    bindMethodology(state);
    bindResponsiveBehavior(state);
    applyVisibility(state, false);
    page.dataset.studioMounted = "true";
    page.__studioState = state;
    startRelativeAgeRefresh(state);
    loadDashboardData(state);
    return state;
  }

  function ready(scope) {
    if (!scope) {
      return;
    }
    if (scope.readyState === "loading") {
      scope.addEventListener("DOMContentLoaded", () => mount(scope), { once: true });
      return;
    }
    mount(scope);
  }

  return {
    CHART_STYLES,
    RANGE_OPTIONS,
    addressCopyLabel,
    aggregateSankeyRows,
    allowedChartStyles,
    buildCsv,
    chartPresentation,
    chartAnimationConfig,
    classifySourceFreshness,
    compactNumber,
    compareValues,
    concentrationModel,
    counterValueForRows,
    createZip,
    csvEscape,
    dashboardExportFilename,
    dashboardGeneratedDate,
    dateStamp,
    defaultChartStyle,
    deriveTableView,
    explorerUrl,
    filterTableRows,
    filterRowsByRange,
    finiteNumber,
    formatCompactDisplayValue,
    formatTooltipValue,
    formatValue,
    growthAxisIndex,
    growthChartModel,
    growthChartView,
    growthChartViews,
    growthDynamicStackEnabled,
    growthProjectedExportRows,
    growthDynamicCategoryPlan,
    growthRankingVisibleRows,
    growthVisibleCategorySettings,
    growthTooltipFormat,
    isSourceStale,
    intelligenceRowsForComponent,
    intelligenceWalletForAddress,
    intelligenceWallets,
    latestDate,
    loadStudioSources,
    metricCsvEntry,
    metricExportFilename,
    metricGeneratedDate,
    metricSourceNotice,
    methodologyDetails,
    momentumChartModel,
    momentumFilterOptions,
    chartPeriodLabel,
    momentumValueAxisUsesScale,
    momentumWeekStart,
    mount,
    navigateToSelection,
    normalizeChain,
    normalizeDemoBundle,
    normalizeGeneratedQuery,
    normalizeGeneratedDerived,
    normalizeManifest,
    normalizeRefreshStatus,
    panelToggleModel,
    periodKeyForMetric,
    rangeCutoff,
    rawRowsForMetric,
    ready,
    relativeAgeLabel,
    rowsToCsv: buildCsv,
    selectedMetricCsvEntries,
    selectPeriodRow,
    sectionNavId,
    setActiveSectionNav,
    shortAddress,
    normalizeWalletAddress,
    sankeyConservation,
    sankeyNodeId,
    sortRows,
    sortTableRows: sortRows,
    sparklineGeometry,
    stackedBarBorderRadius,
    stackedBarSeriesData,
    stableBarInteraction,
    utcTimestampDetailLabel,
    utcTimestampLabel,
    updateDashboardTimestamp,
    validateExpectedColumns,
    visibilityDisclosureModel,
    visibilityDisclosureStorageKey,
    visibilityStorageKey,
  };
});
