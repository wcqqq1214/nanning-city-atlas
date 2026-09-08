import assert from 'node:assert/strict';
import { test } from 'node:test';
import { TapGesture } from '../lib/city/tap-gesture.ts';

const finger = (pointerId, x = 100, y = 100, button = 0) => ({
  pointerId,
  clientX: x,
  clientY: y,
  button,
});

test('a stationary primary pointer selects a landmark, including small finger jitter', () => {
  const tap = new TapGesture();
  tap.start(finger(1));
  assert.equal(tap.end(finger(1, 103, 102)), true);
});
test('pinching cannot select a landmark when either finger is released first', () => {
  for (const first of [1, 2]) {
    const tap = new TapGesture();
    tap.start(finger(1));
    tap.start(finger(2, 160));
    assert.equal(tap.end(finger(first)), false);
    assert.equal(tap.end(finger(3 - first)), false);
    tap.start(finger(3));
    assert.equal(tap.end(finger(3)), true);
  }
});
test('a pan that returns to its origin is still a drag', () => {
  const tap = new TapGesture();
  tap.start(finger(1));
  tap.move(finger(1, 130));
  tap.move(finger(1));
  assert.equal(tap.end(finger(1)), false);
});
test('DOM event fields inherited from a prototype are retained', () => {
  const tap = new TapGesture();
  const event = Object.create(finger(9));
  tap.start(event);
  assert.equal(tap.end(event), true);
});
test('cancelled and secondary pointers do not select', () => {
  const tap = new TapGesture();
  tap.start(finger(1));
  tap.cancel(finger(1));
  assert.equal(tap.end(finger(1)), false);
  tap.start(finger(2, 100, 100, 2));
  assert.equal(tap.end(finger(2, 100, 100, 2)), false);
});
