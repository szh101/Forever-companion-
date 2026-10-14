"""Lua 5.1 contracts with synthetic APIs; not a live WoW compatibility claim."""
import json
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime
from companion.core import parse_snapshot

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
SECRET = {}
function issecretvalue(v) return v == SECRET end
function InCombatLockdown() return false end
function GetBuildInfo() return "1.60.1", "test-build", "test", 16001 end
function GetServerTime() return TEST_NOW end
function GetLocale() return "zhCN" end
function UnitLevel() return 12 end
function UnitClass() return "战士", "WARRIOR" end
function UnitFactionGroup() return "Alliance" end
function UnitGUID() return "target-fixture" end
function GetZoneText() return "测试区域" end
function GetInventoryItemLink(unit, slot)
    if slot == 16 then return "|cffffffff|Hitem:123:0|h[测试物品]|h|r" end
end
C_QuestLog = {
    GetNumQuestLogEntries = function() return 3 end,
    GetInfo = function(i)
        if i == 1 then return {isHeader=true, title="区域"} end
        if i == 2 then return {questID=123, title="测试任务", level=12, isHeader=false} end
        return nil
    end,
    GetQuestObjectives = function(id) return {{text="测试进度 2/5", numFulfilled=2, numRequired=5, finished=false}} end,
    IsComplete = function() return false end
}
C_Map = {
    GetBestMapForUnit = function() return 999 end,
    GetPlayerMapPosition = function() return { GetXY = function() return 0.25, 0.5 end } end
}
SlashCmdList = {}
UIParent = {}
ChatFontNormal = {}
MESSAGES = {}
DEFAULT_CHAT_FRAME = {AddMessage=function(_, text) MESSAGES[#MESSAGES+1]=text end}
CONTROL_DOWN = false
META_DOWN = false
function IsControlKeyDown() return CONTROL_DOWN end
function IsMetaKeyDown() return META_DOWN end
function IsMacClient() return true end
function CopyToClipboard() error("Restricted clipboard API must not be called") end
FRAMES = {}
function CreateFrame(kind, name)
    local f = {kind=kind, name=name, scripts={}, TitleText={SetText=function() end}}
    setmetatable(f, {__index=function(t,k)
        if k == "SetScript" then return function(self, name, fn) self.scripts[name]=fn end end
        if k == "CreateFontString" then return function() return setmetatable({}, {__index=function() return function() end end}) end end
        if k == "SetText" then return function(self, value) self.text=value end end
        if k == "SetAlpha" then return function(self, value) self.alpha=value end end
        if k == "SetFocus" then return function(self) self.focused=true end end
        if k == "ClearFocus" then return function(self) self.focused=false end end
        if k == "HighlightText" then return function(self) self.selected=self.text end end
        if k == "Hide" then return function(self)
            self.hidden=true
            if self.scripts.OnHide then self.scripts.OnHide(self) end
        end end
        if k == "Show" then return function(self) self.hidden=false end end
        return function() end
    end})
    FRAMES[#FRAMES+1] = f
    if name then _G[name]=f end
    return f
end
'''


class AddonTests(unittest.TestCase):
    def setUp(self):
        import time
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().TEST_NOW = int(time.time())
        self.lua.execute(HARNESS)
        for name in ("ForeverAI.lua", "Snapshot.lua"):
            self.lua.execute((ROOT / "addon/ForeverAI" / name).read_text(encoding="utf-8"))

    def collect(self):
        return json.loads(self.lua.eval("ForeverAI.Encode(ForeverAI.Collect())"))

    def test_round_trip_real_collector_to_companion_parser(self):
        data = self.collect()
        parse_snapshot(json.dumps(data))
        self.assertEqual(data["quests"][0]["objectives"][0]["fulfilled"], 2)
        self.assertEqual(data["equipment"][0]["id"], 123)
        self.assertEqual(data["omittedQuests"], 1)
        self.assertEqual(data["questStatus"], "partial: unavailable entries")
        self.assertNotIn("name", data["player"])
        self.assertEqual(data["x"], 0.25)

    def test_combat_and_secret_state_fail_closed(self):
        for result in ["true", "SECRET"]:
            self.lua.execute(f"function InCombatLockdown() return {result} end")
            value, error = self.lua.eval("ForeverAI.Collect()")
            self.assertIsNone(value)
            self.assertIn("combat", error)

    def test_missing_and_secret_data_not_serialized(self):
        self.lua.execute("C_QuestLog.GetInfo=function() return SECRET end; C_Map=nil")
        data = self.collect()
        self.assertEqual(data["quests"], [])
        self.assertEqual(data["omittedQuests"], 3)
        self.assertNotIn("x", data)

    def test_json_escaping_without_execution(self):
        text = '中文\n"\\\x01 ]]); os.execute("bad"); --'
        self.lua.globals().TEST_TEXT = text
        self.assertEqual(json.loads(self.lua.eval("ForeverAI.Encode(TEST_TEXT)")), text)

    def test_manual_inspection_cache_cleared_on_target_change(self):
        self.lua.execute('FRAMES[1].scripts.OnEvent(nil, "INSPECT_READY", "target-fixture")')
        self.assertEqual(self.collect()["inspectedEquipment"][0]["id"], 123)
        self.lua.execute('FRAMES[1].scripts.OnEvent(nil, "PLAYER_TARGET_CHANGED")')
        self.assertNotIn("inspectedEquipment", self.collect())

    def test_export_panel_constructs(self):
        self.lua.execute("SlashCmdList.FOREVERAI()")
        edit = next(f for f in self.lua.globals().FRAMES.values() if f.kind == "EditBox")
        self.assertEqual(edit.alpha, 0)
        self.assertTrue(edit.focused)
        self.assertEqual(edit.selected, edit.text)
        self.assertEqual(parse_snapshot(edit.text)["quests"][0]["id"], 123)
        # Re-preparing restores the full original payload if text was edited.
        original = edit.text
        edit.text = "accidental input"
        edit.scripts.OnTextChanged(edit, True)
        self.assertEqual(edit.text, original)
        self.lua.execute("ForeverAIPrepareCopyButton.scripts.OnClick()")
        self.assertEqual(edit.selected, original)
        self.assertEqual(len(self.lua.globals().MESSAGES), 0)

    def test_copy_shortcuts_close_and_release_keyboard_without_false_success(self):
        for modifier in ("CONTROL_DOWN", "META_DOWN"):
            self.lua.execute("SlashCmdList.FOREVERAI()")
            edit = next(f for f in self.lua.globals().FRAMES.values() if f.kind == "EditBox")
            panel = self.lua.globals().ForeverAISnapshotPanel
            edit.scripts.OnKeyUp(edit, "C")
            self.assertFalse(panel.hidden)
            self.lua.globals()[modifier] = True
            edit.scripts.OnKeyUp(edit, "C")
            self.lua.globals()[modifier] = False
            self.assertTrue(panel.hidden)
            self.assertFalse(edit.focused)
            self.assertEqual(edit.text, "")
            messages = list(self.lua.globals().MESSAGES.values())
            self.assertTrue(all("已复制" not in text for text in messages))
            self.assertIn("粘贴 addon", messages[-1])

    def test_copy_panel_escape_and_combat_release_keyboard(self):
        for event in ("OnEscapePressed", "OnEvent"):
            self.lua.execute("SlashCmdList.FOREVERAI()")
            edit = next(f for f in self.lua.globals().FRAMES.values() if f.kind == "EditBox")
            panel = self.lua.globals().ForeverAISnapshotPanel
            (edit.scripts if event == "OnEscapePressed" else panel.scripts)[event]()
            self.assertFalse(edit.focused)
            self.assertTrue(panel.hidden)


if __name__ == "__main__":
    unittest.main()
