import assert from 'node:assert/strict';
import {visitState} from '../web/factory-view.js';
for(const stage of ['transport','assembly','inspection']) {
 const visits=[{stage,start:470,end:480,completed_visit:false}];
 assert.equal(visitState(visits,480).active.stage,stage);
 assert.equal(visitState(visits,480).last,undefined);
 assert.equal(visitState(visits,475).active.stage,stage);
}
const complete=[{stage:'transport',start:1,end:7,completed_visit:true},{stage:'assembly',start:9,end:19,completed_visit:true}];
assert.equal(visitState(complete,8).last.stage,'transport');
assert.equal(visitState(complete,8).next.stage,'assembly');
assert.equal(visitState(complete,8).active,undefined);
assert.equal(visitState(complete,19).last.stage,'assembly');
console.log('PASS: three truncated horizon stages and completed/queued visit transitions');
