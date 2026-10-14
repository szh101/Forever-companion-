-- Read-only, user-initiated snapshot. No network, saved files or game actions.
ForeverAI = {}
local AI = ForeverAI
local lastInspect

local function secret(value)
    if not issecretvalue then return false end
    local ok, result = pcall(issecretvalue, value)
    return not ok or result == true
end

local function scalar(value)
    if secret(value) then return nil end
    local kind = type(value)
    if kind == "string" then
        -- Do not split a UTF-8 character at the export's string bound.
        local finish = math.min(#value, 3000)
        if finish < #value then
            local nextByte = value:byte(finish + 1)
            while finish > 0 and nextByte and nextByte >= 128 and nextByte < 192 do
                finish = finish - 1; nextByte = value:byte(finish + 1)
            end
        end
        return string.sub(value, 1, finish)
    end
    if kind == "number" then
        if value == value and value ~= math.huge and value ~= -math.huge then return value end
    end
    if kind == "boolean" then return value end
end

local function read(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn, ...)
    if not ok or secret(value) then return nil end
    return value
end

local function field(object, key)
    if secret(object) or type(object) ~= "table" then return nil end
    local ok, value = pcall(function() return object[key] end)
    if ok then return scalar(value) end
end

-- Shared guarded reads for the explicitly enumerated extended collectors.
AI.Secret, AI.Scalar, AI.Read, AI.Field = secret, scalar, read, field

local function quote(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(ch)
        if ch == '"' then return '\\"' end
        if ch == '\\' then return '\\\\' end
        return string.format("\\u%04x", string.byte(ch))
    end) .. '"'
end

function AI.Encode(value)
    if secret(value) then return "null" end
    local kind = type(value)
    if kind == "string" then return quote(value) end
    if kind == "boolean" then return value and "true" or "false" end
    if kind == "number" then return scalar(value) and tostring(value) or "null" end
    if kind ~= "table" then return "null" end
    local parts = {}
    if #value > 0 or next(value) == nil then
        for i = 1, #value do parts[#parts + 1] = AI.Encode(value[i]) end
        return "[" .. table.concat(parts, ",") .. "]"
    end
    for key, entry in pairs(value) do
        if type(key) == "string" then parts[#parts + 1] = quote(key) .. ":" .. AI.Encode(entry) end
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function equipment(unit)
    local items = {}
    for slot = 1, 19 do
        local link = scalar(read(GetInventoryItemLink, unit, slot))
        if type(link) == "string" then
            local id = tonumber(link:match("item:(%d+)"))
            if id then items[#items + 1] = { slot = slot, id = id, link = link } end
        end
    end
    return items
end

function AI.Collect()
    if type(InCombatLockdown) ~= "function" then return nil, "Cannot determine combat state; export stopped." end
    local ok, combat = pcall(InCombatLockdown)
    if not ok or secret(combat) or combat then return nil, "Wait until out of combat to export." end
    local version, build, interface
    if GetBuildInfo then
        local success, v, b, _, i = pcall(GetBuildInfo)
        if success then version, build, interface = scalar(v), scalar(b), scalar(i) end
    end
    local snapshot = {
        kind = "forever-ai-snapshot", schemaVersion = 1,
        capturedAt = scalar(read(GetServerTime)) or scalar(read(time)),
        client = { version = version or "unknown", build = build or "unknown", interface = interface or 0,
                   locale = scalar(read(GetLocale)) or "unknown" },
        player = { level = scalar(read(UnitLevel, "player")) or 0,
                   class = scalar(read(UnitClass, "player")) or "unknown",
                   faction = scalar(read(UnitFactionGroup, "player")) or "unknown" },
        zone = scalar(read(GetZoneText)) or "unknown",
        equipment = equipment("player"), quests = {}, omittedQuests = 0,
        questStatus = "unavailable", inspectionStatus = "not available: inspect the target manually",
    }
    if C_Map then
        local mapID = scalar(read(C_Map.GetBestMapForUnit, "player"))
        snapshot.mapID = mapID
        if mapID then
            local pos = read(C_Map.GetPlayerMapPosition, mapID, "player")
            if pos then
                local success, x, y = pcall(function() return pos:GetXY() end)
                if success then snapshot.x, snapshot.y = scalar(x), scalar(y) end
            end
        end
    end
    if C_QuestLog then
        local count = scalar(read(C_QuestLog.GetNumQuestLogEntries))
        if type(count) == "number" then
            snapshot.questStatus = "collected"
            if count > 150 then snapshot.questStatus = "partial: entry limit" end
            for index = 1, math.min(count, 150) do
                local info = read(C_QuestLog.GetInfo, index)
                local id, title = field(info, "questID"), field(info, "title")
                if field(info, "isHeader") ~= true then
                    if type(id) == "number" and id > 0 and type(title) == "string" then
                        local quest = { id = id, title = title, level = field(info, "level"),
                            complete = scalar(read(C_QuestLog.IsComplete, id)),
                            objectives = {}, objectivesStatus = "unavailable" }
                        local objectives = read(C_QuestLog.GetQuestObjectives, id)
                        if type(objectives) == "table" then
                            -- Stop at the first absent entry without traversing unknown keys.
                            quest.objectivesStatus = "collected"
                            for n = 1, 50 do
                                local success, objective = pcall(function() return objectives[n] end)
                                if not success or secret(objective) then
                                    quest.objectivesStatus = "partial: restricted"; break
                                end
                                if objective == nil then break end
                                local text = field(objective, "text")
                                if text then
                                    quest.objectives[#quest.objectives + 1] = { text = text,
                                        finished = field(objective, "finished"),
                                        fulfilled = field(objective, "numFulfilled"),
                                        required = field(objective, "numRequired") }
                                else quest.objectivesStatus = "partial: unavailable" end
                            end
                        end
                        snapshot.quests[#snapshot.quests + 1] = quest
                    else snapshot.omittedQuests = snapshot.omittedQuests + 1 end
                end
            end
        end
    end
    if lastInspect then
        local guid = scalar(read(UnitGUID, "target"))
        if guid and guid == lastInspect.guid then
            snapshot.inspectedEquipment = lastInspect.items
            snapshot.inspectedAt = lastInspect.at
            snapshot.inspectionStatus = "cached manual inspection; may be incomplete"
        end
    end
    if snapshot.omittedQuests > 0 then snapshot.questStatus = "partial: unavailable entries" end
    if AI.Extend then AI.Extend(snapshot) end
    return snapshot
end

local panel, edit, help, preparedText
local function say(message)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("Forever AI: " .. message) end
end

local function prepareCopy()
    if not preparedText then return end
    edit:SetText(preparedText)
    edit:SetFocus()
    edit:HighlightText()
end

local function showExport()
    local snapshot, err = AI.Collect()
    if not snapshot then
        say(err)
        return
    end
    if not panel then
        panel = CreateFrame("Frame", "ForeverAISnapshotPanel", UIParent, "BasicFrameTemplateWithInset")
        panel:SetSize(320, 148)
        panel:SetPoint("CENTER")
        panel:SetMovable(true)
        panel:EnableMouse(true)
        panel:RegisterForDrag("LeftButton")
        panel:SetScript("OnDragStart", panel.StartMoving)
        panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
        panel.TitleText:SetText("Forever AI")
        help = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        help:SetPoint("TOP", 0, -36)
        help:SetWidth(288)

        -- Keep an ordinary edit box focused for the player's native copy shortcut.
        -- Alpha hides the payload without disabling the widget or its keyboard input.
        -- CopyToClipboard is restricted; addon code never invokes or bypasses it.
        edit = CreateFrame("EditBox", nil, panel)
        edit:SetSize(1, 1)
        edit:SetPoint("CENTER")
        edit:SetAlpha(0)
        edit:SetMultiLine(false)
        edit:SetFontObject(ChatFontNormal)
        edit:SetAutoFocus(false)
        edit:SetMaxLetters(0)
        edit:SetMaxBytes(0)
        edit:SetScript("OnEscapePressed", function() panel:Hide() end)
        edit:SetScript("OnEnterPressed", function() panel:Hide() end)
        edit:SetScript("OnTextChanged", function(_, userInput)
            if userInput then prepareCopy() end
        end)
        edit:SetScript("OnKeyUp", function(_, key)
            if key == "C" and (IsControlKeyDown() or (IsMetaKeyDown and IsMetaKeyDown())) then
                -- A key event is not proof of OS clipboard contents. Only the
                -- companion can confirm a successful import after validation.
                panel:Hide()
                say("请到 Forever AI 助手点击「粘贴 addon」。")
            end
        end)
        panel:SetScript("OnHide", function()
            edit:ClearFocus()
            edit:SetText("")
            preparedText = nil
        end)
        panel:RegisterEvent("PLAYER_REGEN_DISABLED")
        panel:SetScript("OnEvent", function() panel:Hide() end)

        local copy = CreateFrame("Button", "ForeverAIPrepareCopyButton", panel, "UIPanelButtonTemplate")
        copy:SetSize(136, 26)
        copy:SetPoint("BOTTOM", 0, 14)
        copy:SetText("准备复制")
        copy:SetScript("OnClick", prepareCopy)
    end
    preparedText = AI.Encode(snapshot)
    if #preparedText > 190000 then
        panel:Hide()
        edit:ClearFocus()
        edit:SetText("")
        preparedText = nil
        say("快照超过安全大小，未准备复制；请更新插件后重试。")
        return
    end
    local shortcut = (IsMacClient and IsMacClient()) and "Command+C（或 Ctrl+C）" or "Ctrl+C"
    local categories = snapshot.coverageSummary and (snapshot.coverageSummary.collected + snapshot.coverageSummary.partial) or 0
    help:SetText(#snapshot.quests .. " 个任务 · " .. categories .. " 类资料已准备好\n按 " .. shortcut .. "，再到助手粘贴")
    panel:Show()
    prepareCopy()
end

SLASH_FOREVERAI1 = "/fai"
SlashCmdList.FOREVERAI = showExport
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_TARGET_CHANGED")
events:RegisterEvent("INSPECT_READY")
events:SetScript("OnEvent", function(_, event, guid)
    if event == "PLAYER_TARGET_CHANGED" then lastInspect = nil; return end
    if secret(guid) or type(guid) ~= "string" then return end
    local target = scalar(read(UnitGUID, "target"))
    if target and target == guid then
        lastInspect = { guid = guid, items = equipment("target"), at = scalar(read(GetServerTime)) }
    end
end)
