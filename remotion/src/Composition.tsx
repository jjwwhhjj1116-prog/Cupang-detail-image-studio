import React, {useEffect, useState} from "react";
import {Video} from "@remotion/media";
import {loadFont} from "@remotion/fonts";
import {AbsoluteFill, Composition, Sequence, cancelRender, continueRender, delayRender, interpolate, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

type TextLayer = {text:string; position:number[]; alignment:number; font_size:number; color:string;
  start:number; end:number; entry_seconds:number; start_scale:number; slide_px:number; outline_width:number};
type Shot = {start:number; end:number; overlay_mode?:string; text_layers?:TextLayer[];
  display_caption:string; position?:number[]; alignment?:number; font_size?:number; color?:string;
  entry_seconds?:number; slide_px?:number};
type Props = {sourceFile:string; fontFile:string|null; captionMode:string; design:{shots:Shot[]}};

const Layer:React.FC<{layer:TextLayer; sceneStart:number}> = ({layer,sceneStart}) => {
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const begin=(layer.start-sceneStart)*fps;
  if(frame < begin || frame >= (layer.end-sceneStart)*fps) return null;
  const align=layer.alignment%3;
  const anchor=align===1?"0%":align===2?"-50%":"-100%";
  return <div style={{position:"absolute",left:layer.position[0],top:layer.position[1],
    fontFamily:"GmarketLocalBold",fontSize:layer.font_size,lineHeight:1.18,fontWeight:700,
    color:layer.color==="white"?"white":"#151515",whiteSpace:"pre",textAlign:align===1?"left":align===2?"center":"right",
    WebkitTextStroke:`${layer.outline_width}px ${layer.color==="white"?"#181818":"white"}`,
    paintOrder:"stroke fill",scale:interpolate(frame,[begin,begin+layer.entry_seconds*fps],[layer.start_scale/100,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp"}),
    translate:`${anchor} calc(${layer.alignment<=3?"-100%":"0%"} + ${interpolate(frame,[begin,begin+layer.entry_seconds*fps],[layer.slide_px,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}px)`}}>{layer.text}</div>;
};

const Typography:React.FC<{design:Props["design"];fontFile:string}> = ({design,fontFile}) => {
  const {fps}=useVideoConfig();
  const [handle]=useState(()=>delayRender("Loading verified Gmarket Bold"));
  useEffect(()=>{loadFont({family:"GmarketLocalBold",url:staticFile(fontFile),weight:"700"}).then(()=>{
    if(!document.fonts.check('700 32px "GmarketLocalBold"')) throw new Error("Gmarket font failed to load");
    continueRender(handle);
  }).catch(error=>cancelRender(error));},[fontFile,handle]);
  return <>{design.shots.map((shot,index)=>{
    const layers=shot.overlay_mode==="editorial" ? shot.text_layers??[] : [{text:shot.display_caption,
      position:shot.position??[640,72],alignment:shot.alignment??8,font_size:shot.font_size??60,
      color:shot.color??"white",start:shot.start,end:shot.end,entry_seconds:shot.entry_seconds??.16,
      start_scale:96,slide_px:shot.slide_px??20,outline_width:1.6}];
    return <Sequence key={index} from={shot.start*fps} durationInFrames={(shot.end-shot.start)*fps} premountFor={fps}>
      {layers.map((layer,k)=><Layer key={k} layer={layer} sceneStart={shot.start}/>)}
    </Sequence>;
  })}</>;
};

export const DetailLead:React.FC<Props> = ({sourceFile,fontFile,captionMode,design}) => {
  const {fps}=useVideoConfig();
  return <AbsoluteFill style={{backgroundColor:"#202124"}}>
    {sourceFile ? <Video src={staticFile(sourceFile)} premountFor={fps} objectFit="cover"
      style={{position:"absolute",width:"100%",height:"100%"}}/> : null}
    {captionMode==="with-captions" && fontFile ? <Typography design={design} fontFile={fontFile}/> : null}
  </AbsoluteFill>;
};

export const MyComposition = () => <Composition id="DetailLead" component={DetailLead}
  durationInFrames={150} fps={30} width={1280} height={720}
  defaultProps={{sourceFile:"",fontFile:null,captionMode:"without-captions",design:{shots:[]}}}/>;
