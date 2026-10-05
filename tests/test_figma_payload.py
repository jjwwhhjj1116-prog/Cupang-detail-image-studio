import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("figma_payload", ROOT / "scripts" / "figma_payload.py")
fp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fp)
NODE = os.environ.get("NODE_EXE") or shutil.which("node")

HARNESS = r'''
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
let serial=100, creations=0, fontLoads=0;
const registry=new Map();
class Node {
 constructor(id,name,type,width=780,height=100) {
  Object.assign(this,{id,name,type,width,height,x:0,y:0,children:[],parent:null,fills:[],characters:'sample',fontName:{family:'Pretendard',style:'Bold'}});
  registry.set(id,this);
 }
 appendChild(c) {if(c.parent)c.parent.children=c.parent.children.filter(n=>n!==c);this.children.push(c);c.parent=this;}
 resize(w,h){this.width=w;this.height=h;}
 getStyledTextSegments(){return [{start:0,end:this.characters.length,fontName:this.fontName}];}
 setRangeFontName(start,end,font){this.fontName={...font};this.width+=8;this.height+=2;}
 clone(){const n=new Node('clone:'+serial++,this.name,this.type,this.width,this.height);creations++;n.x=this.x;n.y=this.y;n.characters=this.characters;n.fontName={...this.fontName};n.fills=this.fills.map(f=>({...f}));for(const c of this.children)n.appendChild(c.clone());page.appendChild(n);return n;}
}
const page=new Node('page:live','Templates','PAGE');
const frame=new Node('source:live','6-1','FRAME',780,473);frame.y=10;page.appendChild(frame);
const text=new Node('source:text','Title','TEXT',500,100);frame.appendChild(text);
if(input.sourceFont)text.fontName=input.sourceFont;
const video=new Node('source:video','Group 15','GROUP',688,400);video.y=600;page.appendChild(video);
if(input.specs) {
 page.children=[];page.name=input.pageName;
 for(let i=0;i<input.specs.length;i++) {
  const spec=input.specs[i],root=new Node('live:'+i,spec.name,spec.types[0],spec.width,spec.height);
  root.y=i*1000;page.appendChild(root);
  for(let j=0;j<spec.descendantCount;j++) {
   const n=new Node('live:'+i+':'+j,'Synthetic text '+j,'TEXT',600,40);
   n.characters='검증용 임시 문구 '.repeat(30);n.y=j*40;root.appendChild(n);
  }
 }
}
const files={};
const figma={root:{children:[page]},currentPage:page,mixed:Symbol('mixed'),
 io:{write(name,data){files[name]=data;}},
 async setCurrentPageAsync(p){this.currentPage=p;},async getNodeByIdAsync(id){return registry.get(id)||null;},
 async listAvailableFontsAsync(){return (input.availableFonts||[{family:'Noto Sans KR',style:'Bold'},{family:'Noto Sans KR',style:'Medium'},{family:'Noto Sans KR',style:'Black'}]).map(fontName=>({fontName}));},
 async loadFontAsync(f){fontLoads++;if(input.failFont || f.family===input.missingFamily)throw Error('Font unavailable');},
 createAutoLayout(){creations++;const n=new Node('wrapper:'+serial++,'','FRAME');page.appendChild(n);return n;}
};
async function run(code){return await new (Object.getPrototypeOf(async function(){}).constructor)('figma',code)(figma);}
(async()=>{
 try {
  let result=await run(input.code);
  if(input.nextCode){if(input.stale)text.characters='changed';result=await run(input.nextCode.replace('__SNAPSHOT__',JSON.stringify(result)));}
  if(input.lastCode){const state=result.fullResultFile?JSON.parse(files[result.fullResultFile]):result;result=await run(input.lastCode.replace('__CLONE_STATE__',JSON.stringify(state)));}
  process.stdout.write(JSON.stringify({ok:true,result,creations,fontLoads,sourceText:text.characters,sourceFont:text.fontName,files}));
 }catch(e){process.stdout.write(JSON.stringify({ok:false,error:String(e),creations,fontLoads,sourceText:text.characters}));}
})();
'''


def synthetic_structure():
    return {"template_page":{"name":"Templates"},"source_sha256":"synthetic",
            "types":{"TYPE6":{"sections":[{"section_name":"6-1","offline_frame_id":"offline:1",
            "semantic_role":"lead_1","dimensions":{"width":780,"height":473},
            "video_sibling":{"offline_node_id":"offline:2","name":"Group 15","dimensions":{"width":688,"height":400}}}]}}}


def synthetic_snapshot():
    return {"fileKey":"abcdefgh1234","mode":"source-snapshot","liveVerified":True,"issues":[],
            "templateType":"TYPE6","pageId":"page:live","pageName":"Templates",
            "bindings":[{"liveId":"source:live","sourceSignature":{
                "algorithm":"fnv32x2-utf16-v1","length":0,"nodeCount":1,"hash":"0000000000000000"}}]}


class PayloadTests(unittest.TestCase):
    def test_separate_video_and_duplicate_frame_names_preserved(self):
        structure=fp.read_json(ROOT/'config'/'template-structure.json')
        s=fp.specs_for(structure,'TYPE7')
        duplicate=[x for x in s if x['name']=='7-14']
        self.assertEqual(len(s),22)
        self.assertEqual(len(duplicate),2)
        self.assertEqual({x['height'] for x in duplicate},{1288,749})
        self.assertEqual(len({x['offlineId'] for x in duplicate}),2)
        s6=fp.specs_for(structure,'TYPE6')
        self.assertEqual(len(s6),19)
        self.assertNotIn('6-18',{x['name'] for x in s6})

    def test_archive_or_unverified_snapshot_cannot_clone(self):
        with self.assertRaises(ValueError): fp.file_key('lk-origin-123')
        snapshot=synthetic_snapshot();snapshot['liveVerified']=False
        with self.assertRaises(ValueError): fp.clone_payload(snapshot,'job')
        snapshot=synthetic_snapshot();snapshot['bindings']*=2
        with self.assertRaises(ValueError): fp.clone_payload(snapshot,'job')

    def test_text_rejects_source_ids_and_duplicate_targets(self):
        state={"fileKey":"abcdefgh1234","mode":"clone-result","status":"cloned-not-filled",
               "wrapperId":"clone:root","sourceToClone":{"source:text":"clone:text"}}
        with self.assertRaises(ValueError): fp.text_payload(state,[{"nodeId":"source:text","text":"x","expectedText":"y"}])
        edits=[{"nodeId":"clone:text","text":"x","expectedText":"y"}]*2
        with self.assertRaises(ValueError): fp.text_payload(state,edits)

    @unittest.skipUnless(NODE,"Node is needed for executable Figma adapter tests")
    def test_live_remap_clone_and_preflight_failures(self):
        inspect=fp.inspect_payload('abcdefgh1234',synthetic_structure(),'TYPE6')['code']
        # Substitute the read result into otherwise identical emitted clone code.
        seed=synthetic_snapshot()
        clone=fp.clone_payload(seed,'test-job')['code'].replace('const snapshot = '+fp.js(seed)+';', 'const snapshot = __SNAPSHOT__;')
        def run(**flags):
            p=subprocess.run([NODE,'-e',HARNESS],input=json.dumps({'code':inspect,'nextCode':clone,**flags}),
                             text=True,capture_output=True,check=True,encoding='utf8')
            return json.loads(p.stdout)
        result=run()
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['result']['status'],'cloned-not-filled')
        self.assertEqual([s['role'] for s in result['result']['sections']],['lead_1','lead_1_video'])
        self.assertIn('source:text',result['result']['sourceToClone'])
        self.assertEqual(result['sourceText'],'sample')
        self.assertGreater(result['fontLoads'],0)
        for flags in [{'stale':True},{'failFont':True}]:
            failed=run(**flags)
            self.assertFalse(failed['ok'],failed)
            self.assertEqual(failed['creations'],0,failed)

    @unittest.skipUnless(NODE,"Node is needed for executable Figma adapter tests")
    def test_inspection_is_read_only_and_records_live_id_change(self):
        code=fp.inspect_payload('abcdefgh1234',synthetic_structure(),'TYPE6')['code']
        p=subprocess.run([NODE,'-e',HARNESS],input=json.dumps({'code':code}),text=True,capture_output=True,check=True,encoding='utf8')
        result=json.loads(p.stdout)
        self.assertTrue(result['result']['liveVerified'])
        self.assertEqual(result['creations'],0)
        self.assertFalse(result['result']['bindings'][0]['offlineIdPreserved'])

    @unittest.skipUnless(NODE,"Node is needed for executable Figma adapter tests")
    def test_all_seven_real_template_counts_fit_response_budget(self):
        structure=fp.read_json(ROOT/'config'/'template-structure.json')
        for typ,data in structure['types'].items():
            counts={s['offline_frame_id']:s['descendant_count'] for s in data['sections']}
            specs=[dict(s,descendantCount=counts.get(s['offlineId'],2)) for s in fp.specs_for(structure,typ)]
            code=fp.inspect_payload('abcdefgh1234',structure,typ)['code']
            p=subprocess.run([NODE,'-e',HARNESS],input=json.dumps({'code':code,'specs':specs,'pageName':structure['template_page']['name']}),
                             text=True,capture_output=True,check=True,encoding='utf8')
            result=json.loads(p.stdout)
            with self.subTest(template=typ):
                self.assertTrue(result['ok'],result)
                self.assertTrue(result['result']['liveVerified'])
                self.assertEqual(len(result['result']['bindings']),len(specs))
                self.assertLess(len(json.dumps(result['result'],ensure_ascii=False,indent=2).encode('utf8')),19000)
                self.assertGreater(sum(b['sourceSignature']['length'] for b in result['result']['bindings']),20000)
                self.assertTrue(all('tree' not in b for b in result['result']['bindings']))

    @unittest.skipUnless(NODE,"Node is needed for executable Figma adapter tests")
    def test_large_clone_map_uses_file_and_returns_every_created_id(self):
        structure=fp.read_json(ROOT/'config'/'template-structure.json');typ='TYPE4'
        counts={s['offline_frame_id']:s['descendant_count'] for s in structure['types'][typ]['sections']}
        specs=[dict(s,descendantCount=counts.get(s['offlineId'],2)) for s in fp.specs_for(structure,typ)]
        inspect=fp.inspect_payload('abcdefgh1234',structure,typ)['code']
        seed=synthetic_snapshot();seed['templateType']=typ
        clone=fp.clone_payload(seed,'large-job')['code'].replace('const snapshot = '+fp.js(seed)+';', 'const snapshot = __SNAPSHOT__;')
        p=subprocess.run([NODE,'-e',HARNESS],input=json.dumps({'code':inspect,'nextCode':clone,'specs':specs,'pageName':structure['template_page']['name']}),
                         text=True,capture_output=True,check=True,encoding='utf8')
        result=json.loads(p.stdout)
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['result']['mode'],'clone-result-reference')
        full=json.loads(result['files'][result['result']['fullResultFile']])
        self.assertEqual(full['createdNodeIds'],result['result']['createdNodeIds'])
        self.assertEqual(full['status'],'cloned-not-filled')
        self.assertLess(len(json.dumps(result['result'],ensure_ascii=False,indent=2).encode('utf8')),19000)
        fp.validate_clone(full)

    @unittest.skipUnless(NODE,"Node is needed for executable Figma adapter tests")
    def test_output_overview_and_scoped_pagination(self):
        inspect=fp.inspect_payload('abcdefgh1234',synthetic_structure(),'TYPE6')['code']
        seed=synthetic_snapshot()
        clone=fp.clone_payload(seed,'inspect-job')['code'].replace('const snapshot = '+fp.js(seed)+';', 'const snapshot = __SNAPSHOT__;')
        state={'fileKey':'abcdefgh1234','mode':'clone-result','status':'cloned-not-filled',
               'wrapperId':'clone:root','sourceToClone':{'source:text':'clone:text'}}
        def run(last):
            last=last.replace('const state = '+fp.js(state)+';', 'const state = __CLONE_STATE__;')
            p=subprocess.run([NODE,'-e',HARNESS],input=json.dumps({'code':inspect,'nextCode':clone,'lastCode':last}),
                             text=True,capture_output=True,check=True,encoding='utf8')
            return json.loads(p.stdout)['result']
        overview=run(fp.output_payload(state)['code'])
        self.assertEqual(overview['mode'],'output-overview')
        self.assertEqual(len(overview['sections']),2)
        self.assertNotIn('nodes',overview)
        code=fp.output_payload(state,'selected-section',0,1)['code'].replace('"sectionId":"selected-section"','"sectionId":state.sections[0].cloneId')
        first=run(code)
        self.assertEqual(len(first['nodes']),1)
        self.assertEqual(first['nextOffset'],1)
        self.assertEqual(first['total'],2)
        code=fp.output_payload(state,'selected-section',1,1)['code'].replace('"sectionId":"selected-section"','"sectionId":state.sections[0].cloneId')
        second=run(code)
        self.assertEqual(second['nodes'][0]['type'],'TEXT')
        self.assertIsNone(second['nextOffset'])

    @unittest.skipUnless(NODE,"Node is needed for executable Figma adapter tests")
    def test_explicit_fallback_changes_only_clones_and_keeps_qa_pending(self):
        inspect=fp.inspect_payload('abcdefgh1234',synthetic_structure(),'TYPE6')['code']
        seed=synthetic_snapshot()
        clone=fp.clone_payload(seed,'fallback-job','Noto Sans KR')['code'].replace('const snapshot = '+fp.js(seed)+';', 'const snapshot = __SNAPSHOT__;')
        def run(**flags):
            p=subprocess.run([NODE,'-e',HARNESS],input=json.dumps({'code':inspect,'nextCode':clone,**flags}),
                             text=True,capture_output=True,check=True,encoding='utf8')
            return json.loads(p.stdout)
        result=run(missingFamily='Pretendard',sourceFont={'family':'Pretendard','style':'SemiBold'})
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['sourceFont'],{'family':'Pretendard','style':'SemiBold'})
        change=result['result']['fontChanges'][0]
        self.assertEqual(change['to'],{'family':'Noto Sans KR','style':'Bold'})
        self.assertNotEqual(change['sourceId'],change['cloneId'])
        self.assertNotEqual(change['before']['width'],change['after']['width'])
        self.assertEqual(result['result']['fontQA']['status'],'needs-render-review')
        self.assertTrue(result['result']['masterSignatureVerified'])
        original_supported=run()
        self.assertEqual(original_supported['result']['fontChanges'],[])
        for flags in [{'missingFamily':'Pretendard','availableFonts':[]},
                      {'missingFamily':'Other','sourceFont':{'family':'Other','style':'Bold'}}]:
            failed=run(**flags)
            self.assertFalse(failed['ok'],failed)
            self.assertEqual(failed['creations'],0)


if __name__=='__main__': unittest.main()
