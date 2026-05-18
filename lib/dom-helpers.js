function setNativeValue(el, value) {
  const proto = Object.getPrototypeOf(el);
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const jitter = (base, spread = 0.4) => base + (Math.random() - 0.5) * 2 * spread * base;
