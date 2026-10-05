"""Emit Figma MCP payloads; never perform network calls or mutate a .fig archive.

The Codex workflow executes the returned tool arguments and saves the tool result
locally. This is an agent adapter, not a request for the user to copy scripts.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRUCTURE = ROOT / "config" / "template-structure.json"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def js(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def file_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]{8,80}", value):
        raise ValueError("A verified live Figma fileKey is required; archive lk- keys are invalid.")
    return value


def specs_for(structure, template_type):
    if template_type not in structure["types"]:
        raise ValueError("template_type must be TYPE1 through TYPE7")
    specs = []
    for section in structure["types"][template_type]["sections"]:
        specs.append({"offlineId": section["offline_frame_id"],
                      "name": section["section_name"], "types": ["FRAME"],
                      "role": section["semantic_role"], **section["dimensions"]})
        video = section.get("video_sibling")
        if video:
            # .fig FRAME + resizeToFit may become GROUP in the Plugin API.
            specs.append({"offlineId": video["offline_node_id"],
                          "name": video["name"], "types": ["FRAME", "GROUP"],
                          "role": section["semantic_role"] + "_video", **video["dimensions"]})
    if len({s["offlineId"] for s in specs}) != len(specs):
        raise ValueError("Duplicate offline source ID in template registry")
    return specs


COMMON = r'''
function flat(root) {
  const out = [];
  function walk(n) { out.push(n); if ('children' in n) for (const c of n.children) walk(c); }
  walk(root); return out;
}
function currentFonts(n) {
  if (n.type !== 'TEXT') return [];
  const fonts = n.getStyledTextSegments(['fontName']).map(s => s.fontName);
  if (!fonts.length && n.fontName !== figma.mixed) fonts.push(n.fontName);
  return fonts;
}
function summary(n) {
  const v = {id:n.id, name:n.name, type:n.type, parentId:n.parent ? n.parent.id : null};
  if ('width' in n) Object.assign(v, {width:n.width,height:n.height,x:n.x,y:n.y});
  if ('children' in n) v.childIds = n.children.map(c => c.id);
  if (n.type === 'TEXT') Object.assign(v, {characters:n.characters,fonts:currentFonts(n),
    componentPropertyReferences:n.componentPropertyReferences || null});
  if ('fills' in n && Array.isArray(n.fills)) v.imageFills = n.fills
    .filter(p => p.type === 'IMAGE').map(p => ({imageHash:p.imageHash,scaleMode:p.scaleMode}));
  return v;
}
function brief(n) {
  return {id:n.id,name:n.name,type:n.type,parentId:n.parent ? n.parent.id : null,
    width:n.width,height:n.height,x:n.x,y:n.y,childCount:'children' in n ? n.children.length : 0};
}
function signature(nodes) {
  const text=JSON.stringify(nodes.map(summary));
  let a=2166136261,b=3339675911;
  for(let i=0;i<text.length;i++) {const c=text.charCodeAt(i);a=Math.imul(a^c,16777619)>>>0;b=Math.imul(b^c,2246822519)>>>0;}
  return {algorithm:'fnv32x2-utf16-v1',length:text.length,nodeCount:nodes.length,
    hash:a.toString(16).padStart(8,'0')+b.toString(16).padStart(8,'0')};
}
function jsonBytes(value,pretty=false) {
  let bytes=0;
  for(const c of JSON.stringify(value,null,pretty?2:undefined)) {const n=c.codePointAt(0);bytes+=n<=127?1:n<=2047?2:n<=65535?3:4;}
  return bytes;
}
async function fontsReady(nodes) {
  const fonts = new Map();
  for (const n of nodes) for (const f of currentFonts(n)) fonts.set(JSON.stringify(f),f);
  await Promise.all([...fonts.values()].map(f => figma.loadFontAsync(f)));
  return [...fonts.values()];
}
'''


def payload(key, code, description, write=False):
    return {"fileKey": file_key(key), "code": code,
            "description": description,
            "skillNames": "figma-use,figma-generate-design" if write else "figma-use"}


def inspect_payload(key, structure, template_type, page_id=None):
    specs = specs_for(structure, template_type)
    selector = {"id": page_id, "name": structure["template_page"]["name"]}
    code = COMMON + "\nconst requested = " + js(selector) + ";\nconst specs = " + js(specs) + r''';
const pages = figma.root.children.filter(p => requested.id ? p.id === requested.id : p.name === requested.name);
if (pages.length !== 1) throw new Error('Template page missing or ambiguous; discover pages first.');
const page = pages[0]; await figma.setCurrentPageAsync(page);
const bindings = [], issues = [];
for (const spec of specs) {
  const matches = page.children.filter(n => n.name === spec.name && spec.types.includes(n.type)
    && Math.abs(n.width-spec.width) <= 0.1 && Math.abs(n.height-spec.height) <= 0.1);
  if (matches.length !== 1) { issues.push({offlineId:spec.offlineId,name:spec.name,candidateIds:matches.map(n=>n.id)}); continue; }
  const n = matches[0];
  bindings.push({offlineId:spec.offlineId,role:spec.role,liveId:n.id,
    offlineIdPreserved:n.id===spec.offlineId,root:brief(n),sourceSignature:signature(flat(n))});
}
bindings.sort((a,b)=>a.root.y-b.root.y || a.root.x-b.root.x);
return {schemaVersion:1,mode:'source-snapshot',fileKey:'''+js(key)+r''',templateType:'''+js(template_type)+r''',
  pageId:page.id,pageName:page.name,sourceSha256:'''+js(structure["source_sha256"])+r''',
  liveVerified:issues.length===0,bindings,issues,createdNodeIds:[],mutatedNodeIds:[]};
'''
    return payload(key, code, "Read and bind " + template_type + " source templates; no mutations")


def validate_snapshot(snapshot):
    file_key(snapshot.get("fileKey"))
    if snapshot.get("mode") != "source-snapshot" or snapshot.get("liveVerified") is not True:
        raise ValueError("clone requires a successful live source-snapshot, not archive IDs")
    if snapshot.get("issues") or not snapshot.get("bindings"):
        raise ValueError("Unresolved source bindings")
    ids = [b["liveId"] for b in snapshot["bindings"]]
    if len(set(ids)) != len(ids):
        raise ValueError("A live source node is bound more than once")
    for binding in snapshot["bindings"]:
        sig = binding.get("sourceSignature", {})
        if sig.get("algorithm") != "fnv32x2-utf16-v1" or not re.fullmatch(r"[0-9a-f]{16}", sig.get("hash", "")):
            raise ValueError("Fresh compact source signatures are required; re-run inspect")


def clone_payload(snapshot, job_id):
    validate_snapshot(snapshot)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
        raise ValueError("job_id must use 1-80 letters, digits, underscores or hyphens")
    wrapper_name = "상세페이지 · " + job_id + " · " + snapshot["templateType"]
    code = COMMON + "\nconst snapshot = " + js(snapshot) + ";\nconst wrapperName = " + js(wrapper_name) + r''';
const page = await figma.getNodeByIdAsync(snapshot.pageId);
if (!page || page.type !== 'PAGE' || page.name !== snapshot.pageName) throw new Error('Source page changed.');
await figma.setCurrentPageAsync(page);
if (page.children.some(n=>n.name===wrapperName)) throw new Error('Job wrapper already exists. Inspect it and resume; do not clone again.');
const sources = [];
for (const binding of snapshot.bindings) {
  const n = await figma.getNodeByIdAsync(binding.liveId);
  if (!n || n.parent?.id !== page.id || !['FRAME','GROUP'].includes(n.type)) throw new Error('Source no longer valid: '+binding.liveId);
  if (JSON.stringify(signature(flat(n))) !== JSON.stringify(binding.sourceSignature)) throw new Error('Source changed since inspection: '+binding.liveId);
  sources.push({binding,node:n});
}
// All identity, type, geometry, content and font checks precede any mutation.
const sourceNodes = sources.flatMap(s=>flat(s.node));
const loadedFonts = await fontsReady(sourceNodes);
let right = 0; for (const n of page.children) right = Math.max(right,n.x+n.width);
const createdNodeIds = [], sourceToClone = {}, sections = [];
function finish(result) {
  if(jsonBytes(result,true)<=16000) return result;
  const name='''+js(job_id + "-clone-state.json")+r''';
  figma.io.write(name,JSON.stringify(result));
  return {mode:'clone-result-reference',status:result.status,fullResultFile:name,
    fileKey:result.fileKey,pageId:result.pageId,wrapperId:result.wrapperId,wrapperName:result.wrapperName,
    createdNodeIds:result.createdNodeIds,mutatedNodeIds:result.mutatedNodeIds,
    sourceMapEntryCount:Object.keys(result.sourceToClone).length,masterMutated:false,
    error:result.error,safeToRetryWithoutCanvasRead:result.safeToRetryWithoutCanvasRead};
}
if(typeof figma.io?.write !== 'function' && sourceNodes.length>250) throw new Error('Full clone-state artifact output is unavailable; no changes made.');
let wrapper;
try {
  wrapper = figma.createAutoLayout('VERTICAL'); createdNodeIds.push(wrapper.id);
  wrapper.name = wrapperName; wrapper.resize(780,100);
  wrapper.layoutSizingHorizontal='FIXED'; wrapper.layoutSizingVertical='HUG';
  wrapper.primaryAxisAlignItems='MIN'; wrapper.counterAxisAlignItems='CENTER';
  wrapper.paddingTop=0; wrapper.paddingBottom=0; wrapper.paddingLeft=0; wrapper.paddingRight=0;
  wrapper.itemSpacing=0; wrapper.fills=[]; wrapper.x=right+200; wrapper.y=0; wrapper.placeholder=true;
  for (const {binding,node} of sources) {
    const copy = node.clone();
    const originals=flat(node), copies=flat(copy); createdNodeIds.push(...copies.map(n=>n.id));
    if (originals.length !== copies.length) throw new Error('Clone hierarchy changed; inspect partial result.');
    for (let i=0;i<originals.length;i++) {
      if (originals[i].name!==copies[i].name || originals[i].type!==copies[i].type) throw new Error('Clone tree mismatch; inspect partial result.');
      sourceToClone[originals[i].id]=copies[i].id;
    }
    wrapper.appendChild(copy);
    copy.layoutSizingHorizontal='FIXED'; copy.layoutSizingVertical='FIXED';
    sections.push({role:binding.role,offlineId:binding.offlineId,sourceId:node.id,cloneId:copy.id,
      sourceName:node.name,width:copy.width,height:copy.height});
  }
  return finish({schemaVersion:1,mode:'clone-result',status:'cloned-not-filled',fileKey:snapshot.fileKey,
    pageId:page.id,templateType:snapshot.templateType,wrapperId:wrapper.id,wrapperName,
    sections,sourceToClone,loadedFonts,createdNodeIds,mutatedNodeIds:[],masterMutated:false});
} catch (error) {
  return finish({schemaVersion:1,mode:'clone-result',status:'partial',fileKey:snapshot.fileKey,
    pageId:page.id,templateType:snapshot.templateType,wrapperId:wrapper?.id,wrapperName,
    sections,sourceToClone,createdNodeIds,mutatedNodeIds:[],masterMutated:false,
    error:String(error),safeToRetryWithoutCanvasRead:false});
}
'''
    return payload(snapshot["fileKey"], code, "Clone verified templates for " + job_id + "; preserve master", True)


def validate_clone(state):
    file_key(state.get("fileKey"))
    if state.get("mode") != "clone-result" or state.get("status") != "cloned-not-filled":
        raise ValueError("A complete clone-result is required")
    if not state.get("wrapperId") or not state.get("sourceToClone"):
        raise ValueError("Clone map is missing")
    if state["wrapperId"] in state["sourceToClone"]:
        raise ValueError("Wrapper is a source node")
    if set(state["sourceToClone"]) & set(state["sourceToClone"].values()):
        raise ValueError("Clone IDs overlap source IDs")


def output_payload(state, section_id=None, offset=0, limit=20):
    validate_clone(state)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("offset must be nonnegative and limit must be 1..100")
    options = {"sectionId": section_id, "offset": offset, "limit": limit}
    code = COMMON + "\nconst state = " + js(state) + ";\nconst options = " + js(options) + r''';
const page = await figma.getNodeByIdAsync(state.pageId);
if (!page || page.type!=='PAGE') throw new Error('Output page missing');
await figma.setCurrentPageAsync(page);
const wrapper = await figma.getNodeByIdAsync(state.wrapperId);
if (!wrapper || wrapper.type!=='FRAME' || wrapper.name!==state.wrapperName || wrapper.parent?.id!==page.id) throw new Error('Output identity changed');
if(!options.sectionId) {
  const nodes=flat(wrapper),counts={}; for(const n of nodes) counts[n.type]=(counts[n.type]||0)+1;
  return {mode:'output-overview',fileKey:state.fileKey,pageId:page.id,wrapper:brief(wrapper),
    counts,nodeCount:nodes.length,sections:wrapper.children.map(brief),createdNodeIds:[],mutatedNodeIds:[]};
}
const scope=await figma.getNodeByIdAsync(options.sectionId);
let ancestor=scope,contained=false;
while(ancestor) {if(ancestor.id===wrapper.id) {contained=true;break;}ancestor=ancestor.parent;}
if(!contained) throw new Error('Inspection scope must be inside the cloned wrapper');
const all=flat(scope),nodes=[];
let next=options.offset;
while(next<all.length && nodes.length<options.limit) {
  const row=summary(all[next]);
  if(jsonBytes(nodes.concat([row]),true)>12000) {
    if(!nodes.length) throw new Error('One node exceeds the response budget; read its text in character slices.');
    break;
  }
  nodes.push(row); next++;
}
return {mode:'output-inspection',fileKey:state.fileKey,pageId:page.id,wrapperId:wrapper.id,
  sectionId:scope.id,total:all.length,offset:options.offset,nextOffset:next<all.length?next:null,
  nodes,createdNodeIds:[],mutatedNodeIds:[]};
'''
    return payload(state["fileKey"], code, "Inspect cloned output and editable text/image slots")


def text_payload(state, edits):
    validate_clone(state)
    allowed = set(state["sourceToClone"].values())
    if not isinstance(edits, list) or not edits:
        raise ValueError("edits must be a nonempty list")
    seen = set()
    for edit in edits:
        if edit.get("nodeId") not in allowed or edit["nodeId"] in seen:
            raise ValueError("Text targets must be distinct cloned IDs")
        if not isinstance(edit.get("text"), str) or not isinstance(edit.get("expectedText"), str):
            raise ValueError("Each edit requires text and expectedText strings from output inspection")
        seen.add(edit["nodeId"])
    code = COMMON + "\nconst state = " + js(state) + ";\nconst edits = " + js(edits) + r''';
const page = await figma.getNodeByIdAsync(state.pageId);
if (!page || page.type!=='PAGE') throw new Error('Output page missing');
await figma.setCurrentPageAsync(page);
const wrapper = await figma.getNodeByIdAsync(state.wrapperId);
if (!wrapper || wrapper.type!=='FRAME' || wrapper.name!==state.wrapperName || wrapper.parent?.id!==page.id) throw new Error('Output identity changed');
const allowed = new Set(Object.values(state.sourceToClone));
const nodes = await Promise.all(edits.map(e=>figma.getNodeByIdAsync(e.nodeId)));
for (let i=0;i<nodes.length;i++) {
  const n=nodes[i]; if (!n || n.type!=='TEXT' || !allowed.has(n.id)) throw new Error('Invalid cloned text target');
  let parent=n.parent,contained=false;
  while (parent) { if(parent.id===wrapper.id) {contained=true;break;} parent=parent.parent; }
  if (!contained || n.characters!==edits[i].expectedText) throw new Error('Text or ancestry changed; re-inspect output');
  if (n.componentPropertyReferences?.characters) throw new Error('Text is controlled by a component property; use the inspected instance setProperties mapping instead.');
}
const loadedFonts=await fontsReady(nodes);
const mutatedNodeIds=[];
try {
  for (let i=0;i<nodes.length;i++) { nodes[i].characters=edits[i].text; mutatedNodeIds.push(nodes[i].id); }
  return {status:'text-applied',createdNodeIds:[],mutatedNodeIds,loadedFonts,nodes:nodes.map(summary)};
} catch(error) {
  return {status:'partial',createdNodeIds:[],mutatedNodeIds,error:String(error),safeToRetryWithoutCanvasRead:false};
}
'''
    return payload(state["fileKey"], code, "Apply checked text edits to cloned nodes with current fonts", True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save tool argument JSON; defaults to stdout")
    sub = parser.add_subparsers(dest="command", required=True)
    pages = sub.add_parser("pages"); pages.add_argument("--file-key", required=True)
    inspect = sub.add_parser("inspect"); inspect.add_argument("--file-key", required=True)
    inspect.add_argument("--type", required=True, choices=[f"TYPE{i}" for i in range(1,8)])
    inspect.add_argument("--page-id"); inspect.add_argument("--structure", type=Path, default=DEFAULT_STRUCTURE)
    clone = sub.add_parser("clone"); clone.add_argument("--snapshot", type=Path, required=True); clone.add_argument("--job-id", required=True)
    output = sub.add_parser("inspect-output"); output.add_argument("--clone-state", type=Path, required=True)
    output.add_argument("--section-id"); output.add_argument("--offset", type=int, default=0); output.add_argument("--limit", type=int, default=20)
    text = sub.add_parser("text"); text.add_argument("--clone-state", type=Path, required=True); text.add_argument("--edits", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "pages":
            result=payload(args.file_key,"return {pages:figma.root.children.map(p=>({id:p.id,name:p.name,type:p.type})),createdNodeIds:[],mutatedNodeIds:[]};","Discover template pages")
        elif args.command == "inspect":
            result=inspect_payload(args.file_key,read_json(args.structure),args.type,args.page_id)
        elif args.command == "clone": result=clone_payload(read_json(args.snapshot),args.job_id)
        elif args.command == "inspect-output": result=output_payload(read_json(args.clone_state),args.section_id,args.offset,args.limit)
        else: result=text_payload(read_json(args.clone_state),read_json(args.edits))
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    serialized=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(serialized,encoding="utf-8")
    else: print(serialized,end="")


if __name__ == "__main__":
    main()
