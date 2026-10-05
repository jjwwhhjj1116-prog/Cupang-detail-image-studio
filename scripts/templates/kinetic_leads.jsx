#target aftereffects
/* Generated project builder. AE execution/rendering has NOT been verified on the authoring PC. */
(function () {
    var data = __JOB_DATA__;
    var i, j, k, file, lead, shot, footage, layer, comp, design, keyword, prop;
    if (app.project && app.project.numItems > 0) {
        throw new Error("Open an empty AE project first. Existing projects are not changed.");
    }
    if ((new File(data.project_path)).exists) {
        throw new Error("Target AEP already exists; generate a new output version.");
    }
    for (i = 0; i < data.leads.length; i++) {
        for (j = 0; j < data.leads[i].shots.length; j++) {
            file = new File(data.workspace + "/" + data.leads[i].shots[j].file);
            if (!file.exists) { throw new Error("Missing source video: " + file.fsName); }
        }
    }
    if (!app.project) { app.newProject(); }
        function transform(item, name) { return item.property("ADBE Transform Group").property(name); }
        function span(item, begin, end) { item.inPoint = begin; item.outPoint = end; }
        function textLayer(target, value, name, size, color, center, begin, end, font) {
            var item = target.layers.addText(value);
            item.name = name;
            var source = item.property("ADBE Text Properties").property("ADBE Text Document");
            var doc = source.value;
            doc.resetCharStyle();
            doc.font = font;
            doc.fontSize = size;
            doc.applyFill = true;
            doc.fillColor = color;
            doc.applyStroke = false;
            doc.justification = ParagraphJustification.CENTER_JUSTIFY;
            source.setValue(doc);
            if (source.value.font !== font) { throw new Error("Requested Korean font is unavailable: " + font); }
            transform(item, "ADBE Anchor Point").expression =
                "var r = sourceRectAtTime(time, false); [r.left + r.width/2, r.top + r.height/2];";
            transform(item, "ADBE Position").setValue(center);
            span(item, begin, end);
            return item;
        }
    app.beginUndoGroup("Build kinetic lead samples");
    try {
        var folder = app.project.items.addFolder(data.job_id + " - KINETIC SAMPLE");
        var footageFolder = app.project.items.addFolder("Original Flow footage");
        footageFolder.parentFolder = folder;
        for (i = 0; i < data.leads.length; i++) {
            lead = data.leads[i];
            design = lead.design;
            comp = app.project.items.addComp(data.job_id + "__" + lead.id + "__KINETIC_SAMPLE",
                                            data.width, data.height, 1, data.duration, data.fps);
            comp.parentFolder = folder;
            comp.workAreaStart = 0;
            comp.workAreaDuration = 5;
            comp.bgColor = [0, 0, 0];
            comp.comment = "Sample creative: black/white/lime, not a confirmed brand-color standard. Five exact 1-second cuts; no added BGM.";
            var background = comp.layers.addSolid([0, 0, 0], "Black background and caption band", data.width, data.height, 1, 5);
            for (j = 0; j < lead.shots.length; j++) {
                shot = lead.shots[j];
                file = new File(data.workspace + "/" + shot.file);
                footage = app.project.importFile(new ImportOptions(file));
                footage.parentFolder = footageFolder;
                footage.name = lead.id + " source " + shot.second;
                if (footage.duration + 0.0001 < shot.source_start + shot.source_duration) {
                    throw new Error("Source is shorter than its selected safe region: " + shot.file);
                }
                layer = comp.layers.add(footage);
                layer.name = "SHOT " + shot.second + " - original source";
                layer.stretch = shot.time_stretch_percent;
                layer.startTime = shot.start - shot.source_start / shot.source_duration;
                layer.frameBlendingType = FrameBlendingType.NO_FRAME_BLEND;
                span(layer, shot.start, shot.end);
                var scale = Math.min(data.width / footage.width, design.content_height / footage.height) * 100;
                transform(layer, "ADBE Scale").setValue([scale, scale]);
                transform(layer, "ADBE Position").setValue([data.width / 2, design.content_height / 2]);
                if (layer.hasAudio) { layer.audioEnabled = data.audio_mode === "preserve"; }
                textLayer(comp, shot.caption, "CAPTION " + shot.second + " - exact full text",
                          design.main_font_size, [1, 1, 1], design.caption_center, shot.start, shot.end, design.font_postscript);
                keyword = textLayer(comp, shot.keyword, "ACCENT " + shot.second, design.accent_font_size,
                                    design.lime_rgb, design.accent_center, shot.start, shot.end, design.font_postscript);
                prop = transform(keyword, "ADBE Position");
                prop.setValueAtTime(shot.start, [design.accent_center[0] - design.accent_slide_px, design.accent_center[1]]);
                prop.setValueAtTime(shot.start + 0.12, design.accent_center);
                prop = transform(keyword, "ADBE Scale");
                for (k = 0; k < design.accent_pop.length; k++) {
                    prop.setValueAtTime(shot.start + design.accent_pop[k].time,
                                       [design.accent_pop[k].scale, design.accent_pop[k].scale]);
                }
                var step = design.progress_width / 5;
                for (k = 0; k < 5; k++) {
                    var barWidth = Math.round(step - design.progress_gap);
                    var color = k < shot.second ? design.lime_rgb : [0.2, 0.2, 0.2];
                    var bar = comp.layers.addSolid(color, "Progress " + shot.second + "-" + (k + 1), barWidth, 4, 1, 5);
                    transform(bar, "ADBE Scale").setValue([100, 50]);
                    transform(bar, "ADBE Position").setValue([design.progress_left + k * step + barWidth / 2, design.progress_y + 1]);
                    span(bar, shot.start, shot.end);
                }
            }
            comp.openInViewer();
        }
        app.project.save(new File(data.project_path));
        alert("Two editable 5-second lead comps created and AEP saved. No render has been run. Inspect typography, source cuts and fonts before rendering.");
    } catch (error) {
        alert("Build stopped: " + error.toString() + "\nPartial items may exist; inspect or Undo before retrying.");
        throw error;
    } finally {
        app.endUndoGroup();
    }
}());
