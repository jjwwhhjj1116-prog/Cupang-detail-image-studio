#target aftereffects
/* v2 editable full-bleed sample builder. Does not render; AE host execution remains unverified. */
(function () {
    var data = __JOB_DATA__;
    var i, j, file, lead, shot, footage, layer, comp, text, source, doc, scale, position, key;
    var imported = {};
    function transform(item, name) { return item.property("ADBE Transform Group").property(name); }
    function span(item, begin, end) { item.inPoint = begin; item.outPoint = end; }
    function editorialText(target, style, design, second) {
        var item = target.layers.addText(style.text);
        item.name = "EDITORIAL " + second + " - " + style.role;
        var prop = item.property("ADBE Text Properties").property("ADBE Text Document");
        var td = prop.value;
        td.resetCharStyle(); td.font = design.font_postscript; td.fontSize = style.font_size;
        td.applyFill = true; td.fillColor = style.color === "white" ? [1, 1, 1] : [0.082, 0.082, 0.082];
        td.applyStroke = style.outline_width > 0;
        td.strokeColor = style.color === "white" ? [0.094, 0.094, 0.094] : [1, 1, 1];
        td.strokeWidth = style.outline_width; td.strokeOverFill = false;
        td.justification = style.alignment === 7 ? ParagraphJustification.LEFT_JUSTIFY :
                           style.alignment === 9 ? ParagraphJustification.RIGHT_JUSTIFY : ParagraphJustification.CENTER_JUSTIFY;
        prop.setValue(td);
        if (prop.value.font !== design.font_postscript) { throw new Error("Install the exact Gmarket Sans TTF Bold font. Source: " + data.font_file); }
        var horizontal = style.alignment === 7 ? "r.left" : style.alignment === 9 ? "r.left+r.width" : "r.left+r.width/2";
        transform(item, "ADBE Anchor Point").expression = "var r=sourceRectAtTime(time,false);[" + horizontal + ",r.top];";
        transform(item, "ADBE Position").setValueAtTime(style.start, [style.position[0], style.position[1] + style.slide_px]);
        transform(item, "ADBE Position").setValueAtTime(style.start + style.entry_seconds, style.position);
        transform(item, "ADBE Scale").setValueAtTime(style.start, [style.start_scale, style.start_scale]);
        transform(item, "ADBE Scale").setValueAtTime(style.start + style.entry_seconds, [100, 100]);
        span(item, style.start, style.end);
    }
    if (app.project && app.project.numItems > 0) { throw new Error("Open an empty AE project first."); }
    if ((new File(data.project_path)).exists) { throw new Error("Choose a new AEP output version."); }
    for (i = 0; i < data.leads.length; i++) {
        for (j = 0; j < data.leads[i].shots.length; j++) {
            file = new File(data.workspace + "/" + data.leads[i].shots[j].file);
            if (!file.exists) { throw new Error("Missing source: " + file.fsName); }
        }
    }
    if (!app.project) { app.newProject(); }
    app.beginUndoGroup("Build fullbleed motion v2 samples");
    try {
        var folder = app.project.items.addFolder(data.job_id + " - FULLBLEED V2");
        var footageFolder = app.project.items.addFolder("Original storyboard sources");
        footageFolder.parentFolder = folder;
        for (i = 0; i < data.leads.length; i++) {
            lead = data.leads[i];
            comp = app.project.items.addComp(data.job_id + "__" + lead.id + "__FULLBLEED_V2", data.width, data.height, 1, 5, 30);
            comp.parentFolder = folder;
            comp.workAreaStart = 0; comp.workAreaDuration = 5;
            comp.comment = "Full bleed. No caption band. Caption mode: " + data.caption_mode + ". One generated storyboard source per lead when using single-source map. AE render not performed.";
            for (j = 0; j < lead.shots.length; j++) {
                shot = lead.shots[j];
                key = data.workspace + "/" + shot.file;
                if (!imported[key]) {
                    imported[key] = app.project.importFile(new ImportOptions(new File(key)));
                    imported[key].parentFolder = footageFolder;
                }
                footage = imported[key];
                if (footage.duration + 0.0001 < shot.source_start + shot.source_duration) { throw new Error("Source selection exceeds footage: " + shot.file); }
                layer = comp.layers.add(footage);
                layer.name = "SHOT " + shot.second + " - safe source window";
                layer.stretch = shot.time_stretch_percent;
                layer.startTime = shot.start - shot.source_start / shot.source_duration;
                layer.frameBlendingType = FrameBlendingType.NO_FRAME_BLEND;
                span(layer, shot.start, shot.end);
                scale = Math.max(data.width / footage.width, data.height / footage.height) * 100;
                transform(layer, "ADBE Scale").setValue([scale, scale]);
                transform(layer, "ADBE Position").setValue([data.width / 2, data.height / 2]);
                if (shot.motion !== "none") {
                    var enlarged = scale * (1 + shot.zoom_amount);
                    var startScale = shot.motion === "zoom-in" ? scale : enlarged;
                    var endScale = shot.motion === "zoom-in" ? enlarged : scale;
                    transform(layer, "ADBE Scale").setValueAtTime(shot.start, [startScale, startScale]);
                    transform(layer, "ADBE Scale").setValueAtTime(shot.end - 1/30, [endScale, endScale]);
                }
                if (layer.hasAudio) { layer.audioEnabled = data.audio_mode === "preserve"; }
                if (data.caption_mode === "without-captions") { continue; }
                if (shot.overlay_mode === "editorial") {
                    for (var k = 0; k < shot.text_layers.length; k++) { editorialText(comp, shot.text_layers[k], lead.design, shot.second); }
                    continue;
                }
                text = comp.layers.addText(shot.display_caption);
                text.name = "CAPTION " + shot.second + " - original full text";
                source = text.property("ADBE Text Properties").property("ADBE Text Document");
                doc = source.value;
                doc.resetCharStyle(); doc.font = lead.design.font_postscript; doc.fontSize = shot.font_size;
                doc.applyFill = true; doc.fillColor = shot.color === "white" ? [1, 1, 1] : [0.082, 0.082, 0.082];
                doc.applyStroke = true; doc.strokeColor = shot.color === "white" ? [0.094, 0.094, 0.094] : [1, 1, 1];
                doc.strokeWidth = 1.6; doc.strokeOverFill = false;
                doc.justification = shot.anchor.indexOf("left") >= 0 ? ParagraphJustification.LEFT_JUSTIFY :
                                    shot.anchor.indexOf("right") >= 0 ? ParagraphJustification.RIGHT_JUSTIFY : ParagraphJustification.CENTER_JUSTIFY;
                source.setValue(doc);
                if (source.value.font !== lead.design.font_postscript) {
                    throw new Error("Install the exact Gmarket Sans TTF Bold font before building. Font source: " + data.font_file);
                }
                var horizontal = shot.anchor.indexOf("left") >= 0 ? "r.left" : shot.anchor.indexOf("right") >= 0 ? "r.left+r.width" : "r.left+r.width/2";
                var vertical = shot.anchor.indexOf("top") === 0 ? "r.top" : "r.top+r.height";
                transform(text, "ADBE Anchor Point").expression = "var r=sourceRectAtTime(time,false);[" + horizontal + "," + vertical + "];";
                position = shot.position;
                transform(text, "ADBE Position").setValueAtTime(shot.start, [position[0], position[1] + shot.slide_px]);
                transform(text, "ADBE Position").setValueAtTime(shot.start + shot.entry_seconds, position);
                transform(text, "ADBE Scale").setValueAtTime(shot.start, [96, 96]);
                transform(text, "ADBE Scale").setValueAtTime(shot.start + shot.entry_seconds, [100, 100]);
                span(text, shot.start, shot.end);
            }
            comp.openInViewer();
        }
        app.project.save(new File(data.project_path));
        alert("Two editable fullbleed comps saved. No render performed. Inspect product crop, overlay positions and original captions.");
    } catch (error) {
        alert("Build stopped: " + error.toString() + "\nPartial items may exist. Inspect or Undo before retrying.");
        throw error;
    } finally { app.endUndoGroup(); }
}());
