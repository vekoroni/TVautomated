'use strict';
const assert = require('node:assert/strict');
const display = require('../../intelligence-lab/static/evening-assessment.js');
const row = Object.freeze({lab_verdict:'MANUAL_REVIEW',lab_rank:7,
  contract_symbol:'SAVED_CONTRACT',evening_assessment_label:'Human review - longer horizon',
  evening_assessment_json:JSON.stringify({version:'evening_opportunity_assessment_v1',
    label:'Human review - longer horizon',scenarios:[]})});
const original = JSON.stringify(row);
let appended = '', writes = 0;
const article = {
  querySelector(selector) {assert.equal(selector,'[data-evening-display-only]');return appended ? {} : null;},
  querySelectorAll() {throw Error('Must not relabel existing card fields');},
  insertAdjacentHTML(position,html) {assert.equal(position,'beforeend');appended=html;writes++;}
};
const host = {querySelector(selector){assert.equal(selector,'.trade-card');return article;}};
display.rows({rows:[row]}, {querySelector(){throw Error('Table must remain unchanged');}});
display.card(row,host);
assert.match(appended,/informational, not a trading gate/);
assert.match(appended,/not counts of viable trades/);
assert.match(appended,/MANUAL_REVIEW/);
display.card(row,host);
assert.equal(writes,1,'Idempotent display');
assert.equal(JSON.stringify(row),original,'No field mutation');
appended='';
display.card({evening_assessment_json:JSON.stringify({version:'evening_opportunity_assessment_v1',scenarios:{}})},host);
assert.match(appended,/invalid saved packet/,'Malformed optional evidence cannot break the card');
assert.match(display.render({}),/not published in this saved revision/);
assert.equal(display.packet({evening_assessment_json:'invalid'}),null);
assert.equal(display.packet({evening_assessment_json:'{"version":"unsupported"}'}),null);
assert(!display.render({evening_assessment_json:JSON.stringify({version:'evening_opportunity_assessment_v1',label:'<script>bad</script>'})}).includes('<script>'));
console.log('PASS: additive card only; no table, verdict, rank, identity or input mutations; idempotent, missing/invalid packets explicit, escaped display');
