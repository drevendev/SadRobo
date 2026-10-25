import test from 'node:test';
import assert from 'node:assert/strict';
import { applyAttribution } from '../scripts/attribution.mjs';

const hash='a'.repeat(64), other='b'.repeat(64);
const stories=()=>[{id:'stable-work',images:[{sha256:hash}],imageVariants:[{sha256:hash},{sha256:other}]}];
const registry=()=>({schemaVersion:1,creators:{
  writer:{name:'A writer'},artist:{name:'An artist',url:'https://example.org/artist'},
  founder:{name:'Project founder'}
},works:{},images:{}});

test('unknown credits and rights never inherit project founders or a blanket license',()=>{
  const works=stories(), report=applyAttribution(works,registry());
  assert.deepEqual(works[0].credits.text.authors,[]);
  assert.equal(works[0].credits.text.status,'unverified');
  assert.equal(works[0].images[0].credits.license.status,'unverified');
  assert.equal(works[0].images[0].credits.license.id,undefined);
  assert.deepEqual(report,{textsVerified:0,textsTotal:1,illustrationsVerified:0,illustrationsTotal:1});
});

test('writer, artist and translator have independent credits and licensing',()=>{
  const works=stories(), data=registry();
  data.works['stable-work']={text:{status:'verified',creatorIds:['writer'],note:'Confirmed by contributor'},
    translations:{en:{status:'partial',creatorIds:['writer','artist']}}};
  data.images[hash]={status:'verified',creatorIds:['artist'],sources:['https://example.org/original'],
    license:{status:'verified',id:'CC-BY-4.0',url:'https://creativecommons.org/licenses/by/4.0/'}};
  const report=applyAttribution(works,data);
  assert.equal(works[0].credits.text.authors[0].name,'A writer');
  assert.equal(works[0].credits.text.license.status,'unverified');
  assert.equal(works[0].images[0].credits.authors[0].name,'An artist');
  assert.equal(works[0].credits.translations.en.authors.length,2);
  assert.equal(report.textsVerified,1);
  assert.equal(report.illustrationsVerified,1);
});

test('a different image hash does not silently inherit confirmed attribution',()=>{
  const works=stories(), data=registry();
  data.images[hash]={status:'verified',creatorIds:['artist'],note:'Verified source file'};
  applyAttribution(works,data);
  assert.equal(works[0].imageVariants[0].credits.status,'verified');
  assert.equal(works[0].imageVariants[1].credits.status,'unverified');
  const reimported=stories();
  applyAttribution(reimported,structuredClone(data));
  assert.deepEqual(reimported[0].credits,works[0].credits);
  assert.deepEqual(reimported[0].images[0].credits,works[0].images[0].credits);
});

test('invalid identity, evidence, status and license references fail the build',()=>{
  const cases=[
    d=>{d.works['stable-work']={text:{creatorIds:['missing']}};},
    d=>{d.works['typo']={};},
    d=>{d.creators.writer.url='javascript:alert(1)';},
    d=>{d.works['stable-work']={text:{status:'verified',creatorIds:['writer']}};},
    d=>{d.works['stable-work']={text:{status:'invalid'}};},
    d=>{d.images[hash]={license:{status:'verified',id:'some-license'}};},
    d=>{d.images[hash]={sources:['data:text/html,test']};},
    d=>{d.images['bad-hash']={};}
  ];
  for(const mutate of cases){const data=registry();mutate(data);assert.throws(()=>applyAttribution(stories(),data));}
});
