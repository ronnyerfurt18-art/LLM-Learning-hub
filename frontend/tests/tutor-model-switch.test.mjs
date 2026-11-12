import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import ts from 'typescript';

// Evaluate the actual JSX disabled expression for a failed, retryable turn.
const source = ts.createSourceFile('LearningTutor.tsx',
  readFileSync(new URL('../src/LearningTutor.tsx', import.meta.url), 'utf8'),
  ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let disabled;
function visit(node) {
  if (ts.isJsxOpeningElement(node) && node.tagName.getText(source) === 'select') {
    const value = node.attributes.properties.find(attribute => attribute.name?.getText(source) === 'value');
    if (value?.initializer?.getText(source) === '{status.provider}') {
      disabled = node.attributes.properties.find(attribute => attribute.name?.getText(source) === 'disabled')
        .initializer.expression.getText(source);
    }
  }
  ts.forEachChild(node, visit);
}
visit(source);
assert.ok(disabled, 'The provider selector must exist');
const isDisabled = new Function('sending', 'switchingModel', 'voice', 'activeTurn', `return ${disabled};`);

test('a failed pending question does not prevent changing models', () => {
  assert.equal(isDisabled(false, false, { busy: false }, { message: 'Failed question' }), false);
});

test('running requests, switches and voice processing still prevent switching', () => {
  assert.equal(isDisabled(true, false, { busy: false }, {}), true);
  assert.equal(isDisabled(false, true, { busy: false }, null), true);
  assert.equal(isDisabled(false, false, { busy: true }, null), true);
});
