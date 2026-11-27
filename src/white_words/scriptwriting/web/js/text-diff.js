window.DASH = window.DASH || {};

// A line diff for the compare screens: `lines` gives every line tagged eq / del / add,
// `collapse` folds long unchanged runs so a one-line edit in a long scene stays readable.
(function (D) {
  const MAX_CELLS = 160000;

  const parts = (s) => (s == null || s === '' ? [] : String(s).split('\n'));
  const eq = (t) => ({ op: 'eq', text: t });
  const del = (t) => ({ op: 'del', text: t });
  const add = (t) => ({ op: 'add', text: t });

  function middle(x, y) {
    if (!x.length || !y.length || x.length * y.length > MAX_CELLS) return x.map(del).concat(y.map(add));
    const w = y.length + 1;
    const t = new Uint32Array((x.length + 1) * w);
    for (let i = x.length - 1; i >= 0; i--) {
      for (let j = y.length - 1; j >= 0; j--) {
        t[i * w + j] = x[i] === y[j] ? t[(i + 1) * w + j + 1] + 1 : Math.max(t[(i + 1) * w + j], t[i * w + j + 1]);
      }
    }
    const out = [];
    let i = 0;
    let j = 0;
    while (i < x.length && j < y.length) {
      if (x[i] === y[j]) { out.push(eq(x[i])); i++; j++; }
      else if (t[(i + 1) * w + j] >= t[i * w + j + 1]) out.push(del(x[i++]));
      else out.push(add(y[j++]));
    }
    while (i < x.length) out.push(del(x[i++]));
    while (j < y.length) out.push(add(y[j++]));
    return out;
  }

  function lines(a, b) {
    const x = parts(a);
    const y = parts(b);
    let head = 0;
    while (head < x.length && head < y.length && x[head] === y[head]) head++;
    let tx = x.length;
    let ty = y.length;
    while (tx > head && ty > head && x[tx - 1] === y[ty - 1]) { tx--; ty--; }
    return x.slice(0, head).map(eq).concat(middle(x.slice(head, tx), y.slice(head, ty)), x.slice(tx).map(eq));
  }

  // Keep `context` unchanged lines around each change; a longer run becomes one gap row.
  function collapse(ops, context) {
    const keep = ops.map(() => false);
    ops.forEach((o, i) => {
      if (o.op === 'eq') return;
      for (let k = Math.max(0, i - context); k <= Math.min(ops.length - 1, i + context); k++) keep[k] = true;
    });
    const out = [];
    let skipped = 0;
    ops.forEach((o, i) => {
      if (keep[i]) {
        if (skipped) { out.push({ op: 'gap', skipped }); skipped = 0; }
        out.push(o);
      } else skipped++;
    });
    if (skipped) out.push({ op: 'gap', skipped });
    return out;
  }

  D.textDiff = { lines, collapse };
})(window.DASH);
