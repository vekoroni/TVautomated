const assert=require('node:assert/strict');
const display=require('../../intelligence-lab/static/evening-assessment.js');
const p={version:'evening_opportunity_assessment_v1',target:111.62,target_label:'First target (median arrival)',
  targets:{full_target:{price:137.47}},scenarios:[{scenario:'TARGET_IF_REACHED',scenario_label:'First target if reached'}]};
const f={evening_assessment_json:JSON.stringify(p),lab_verdict:'MANUAL_REVIEW'};
const before=JSON.stringify(f),html=display.render(f);
assert(html.includes('First target (median arrival) $111.62'));
assert(html.includes('Full target (original Lab): $137.47'));
assert(html.includes('First target if reached'));
assert(html.includes('not time to option profit'));
assert.equal(JSON.stringify(f),before);
const missing=display.render({evening_assessment_json:JSON.stringify({...p,target:0,targets:{first_target:{price:null,state:'UNASSESSED_MISSING_OR_INVALID'}}})});
assert(!missing.includes('First target (median arrival) $0.00'));
console.log('PASS: distinct first/full targets, explicit first-target scenarios, no data mutation');
