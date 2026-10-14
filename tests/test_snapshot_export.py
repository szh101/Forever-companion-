"""Broad Lua exports consumed by the unchanged schema-1 desktop companion."""
import json
from pathlib import Path
import time
import unittest

from lupa.lua51 import LuaRuntime
from companion.core import build_request, parse_snapshot
from test_addon import HARNESS, ROOT

FIXTURE = r'''
function UnitName(unit) return unit == "player" and "测试角色" or "测试目标" end
function GetRealmName() return "测试服务器" end
function UnitRace() return "人类" end
function UnitXP() return 123 end
function UnitXPMax() return 1000 end
function GetMoney() return 123456 end
function GetBindLocation() return "测试旅店" end
function UnitExists(unit) return unit == "player" or unit == "target" end
function IsInGroup() return false end
function UnitStat(unit, index) return 10+index, 12+index, 2, 0 end
function GetInventoryItemDurability() return 15, 30 end
function GetItemInfo() return "测试装备", "item:123", 2, 12, 10, "武器", "剑", 1, "INVTYPE_WEAPON", 1, 100 end
Enum = {SpellBookSpellBank={Player=0}, BankType={Character=0, Account=2}}
NUM_BAG_SLOTS = 0
BANK_READS = 0
C_Container = {
 GetContainerNumSlots=function(bag) if bag==12 then BANK_READS=BANK_READS+1 end return 2 end,
 GetContainerNumFreeSlots=function() return 1, 0 end,
 GetBagName=function() return "测试容器" end,
 HasContainerItem=function(bag,slot) return slot==1 end,
 GetContainerItemInfo=function(bag,slot)
   if slot==1 then return {itemID=bag==12 and 777 or 123, itemName="测试材料", stackCount=5, quality=1, isBound=false} end
 end
}
C_Bank = {CanViewBank=function(t) return t==0 end, FetchPurchasedBankTabIDs=function() return {12} end}
function GetProfessions() return 1 end
function GetProfessionInfo() return "测试炼金", nil, 55, 75, 1, 0, 171, 0 end
C_SkillInfo = {GetNumSkillLines=function() return 1 end,
 GetSkillLineInfo=function() return {skillID=171,name="测试炼金",rank=55,maxRank=75,isHeader=false} end}
C_Reputation = {GetNumFactions=function() return 1 end,
 GetFactionDataByIndex=function() return {factionID=72,name="测试声望",currentStanding=1234,reaction=4,isHeader=false} end}
C_CurrencyInfo = {GetCurrencyListSize=function() return 1 end,
 GetCurrencyListInfo=function() return {name="测试代币",quantity=7,isHeader=false} end}
C_SpellBook = {GetNumSpellBookSkillLines=function() return 1 end,
 GetSpellBookSkillLineInfo=function() return {name="测试技能",itemIndexOffset=0,numSpellBookItems=1} end,
 GetSpellBookItemInfo=function() return {spellID=567,name="测试法术",isPassive=false} end}
C_ClassTalents = {GetActiveConfigID=function() return 2 end}
C_Traits = {GetConfigInfo=function() return {name="测试配置",treeIDs={3}} end,
 GetTreeNodes=function() return {4,5} end,
 GetNodeInfo=function(config,id) return {activeRank=id==4 and 2 or 0, currentRank=2,activeEntry={entryID=6}} end,
 GetEntryInfo=function() return {definitionID=7} end,
 GetDefinitionInfo=function() return {spellID=567,overrideName="测试天赋"} end}
C_QuestLog.GetAllCompletedQuestIDs=function() return {111,222} end
C_QuestLog.GetNextWaypoint=function() return 999,0.4,0.6 end
C_TradeSkillUI = {IsTradeSkillLinked=function() return false end, IsTradeSkillGuild=function() return false end,
 IsTradeSkillGuildMember=function() return false end, IsNPCCrafting=function() return false end,
 GetBaseProfessionInfo=function() return {professionID=171,professionName="测试炼金"} end,
 GetAllRecipeIDs=function() return {600,601} end,
 GetRecipeInfo=function(id) return {recipeID=id,name="测试配方",learned=id==600} end,
 GetRecipeSchematic=function() return {outputItemID=700,quantityMin=1,quantityMax=1,
   reagentSlotSchematics={{required=true,quantityRequired=2,reagents={{itemID=123}}}}} end}
C_MountJournal = {GetMountIDs=function() return {1,2} end,
 GetMountInfoByID=function(id) return "测试坐骑",888,1,false,true,1,false,false,nil,false,id==1,id end}
C_PetJournal = {GetOwnedPetIDs=function() return {"fixture-private-pet-guid"} end,
 GetPetInfoTableByPetID=function() return {speciesID=50,name="测试伙伴",petLevel=2} end}
function GetTotalAchievementPoints() return 10 end
function GetCategoryList() return {1} end
function GetCategoryNumAchievements() return 2 end
function GetAchievementInfo(category,index) return index,"测试成就",10,index==1,10,1,2026,"desc",0,0,nil,false,true end
function GetNumSavedInstances() return 1 end
function GetSavedInstanceInfo() return "测试副本",123,3600,1,true,false,0,true,40,"普通",5,2 end
'''


class ExpandedSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().TEST_NOW = int(time.time())
        self.lua.execute(HARNESS + FIXTURE)
        # Load the same source list as the game; don't forget a new TOC module.
        addon = ROOT / "addon/ForeverAI"
        for line in (addon / "ForeverAI.toc").read_text().splitlines():
            if line.endswith(".lua"):
                self.lua.execute((addon / line).read_text(encoding="utf-8"))

    def collect(self):
        return parse_snapshot(self.lua.eval("ForeverAI.Encode(ForeverAI.Collect())"))

    def test_broad_snapshot_reaches_existing_provider_without_schema_change(self):
        data = self.collect()
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["addonVersion"], "0.3.0")
        self.assertFalse(data["export"]["completeGameState"])
        self.assertEqual(len(data["coverage"]), 27)
        self.assertEqual(data["player"]["moneyCopper"], 123456)
        self.assertEqual(data["bags"]["entries"][0]["count"], 5)
        self.assertEqual(data["equipmentDetails"]["entries"][0]["durability"], 15)
        self.assertEqual(data["skills"]["entries"][0]["rank"], 55)
        self.assertEqual(data["spellbook"]["entries"][0]["spellID"], 567)
        self.assertEqual(data["talents"]["entries"][0]["activeRank"], 2)
        self.assertEqual(data["completedQuests"]["entries"], [111, 222])
        self.assertEqual(data["quests"][0]["nextWaypoint"]["x"], 0.4)
        self.assertEqual(len(data["mounts"]["entries"]), 1)
        self.assertEqual(data["achievements"]["entries"][0]["earnedByThisCharacter"], True)
        self.assertNotIn("fixture-private-pet-guid", json.dumps(data))
        _, body = build_request("OpenAI", "fixture-model", "材料够不够？", snapshot=data)
        self.assertIn('"moneyCopper": 123456', body["input"][-1]["content"][0]["text"])

    def test_bank_is_unknown_until_open_and_uses_actual_modern_tab_ids(self):
        self.assertEqual(self.collect()["bank"]["status"], "requires_window")
        self.assertEqual(self.lua.globals().BANK_READS, 0)
        self.lua.execute("BankFrame={IsShown=function() return true end}")
        data = self.collect()
        self.assertEqual(data["bank"]["entries"][0]["bag"], 12)
        self.assertEqual(data["bank"]["entries"][0]["id"], 777)
        self.assertEqual(data["bank"]["status"], "partial")  # account bank unavailable
        self.lua.execute("BankFrame.IsShown=function() return false end")
        self.assertEqual(self.collect()["bank"]["entries"], [])

    def test_recipes_have_owner_scope_learned_flags_and_materials(self):
        self.assertEqual(self.collect()["recipes"]["status"], "requires_window")
        self.lua.execute("ProfessionsFrame={IsShown=function() return true end}")
        recipes = self.collect()["recipes"]
        self.assertEqual(recipes["profession"]["professionID"], 171)
        self.assertEqual(recipes["ownership"], "player")
        self.assertEqual([r["learned"] for r in recipes["entries"]], [True, False])
        self.assertEqual(recipes["entries"][0]["reagents"][0]["alternatives"], [{"itemID": 123}])
        self.lua.execute("C_TradeSkillUI.IsTradeSkillLinked=function() return true end")
        self.assertEqual(self.collect()["recipes"]["status"], "unavailable")
        self.lua.execute("C_TradeSkillUI.IsTradeSkillLinked=nil")
        unknown = self.collect()["recipes"]
        self.assertEqual(unknown["ownership"], "unverified-current-view")
        self.assertEqual(unknown["status"], "partial")

    def test_missing_restricted_and_failed_apis_do_not_mean_empty(self):
        self.lua.execute('''
            GetMoney=function() return SECRET end
            C_SpellBook=nil
            GetProfessions=function() error("private raw error") end
            C_Reputation.GetFactionDataByIndex=function() return SECRET end
            C_SkillInfo.GetSkillLineInfo=function() return setmetatable({}, {__index=function() error("restricted") end}) end
            C_Container.GetContainerItemInfo=function() return SECRET end
        ''')
        data = self.collect()
        self.assertNotIn("moneyCopper", data["player"])
        self.assertEqual(data["spellbook"]["status"], "unavailable")
        self.assertEqual(data["professions"]["status"], "unavailable")
        self.assertEqual(data["reputations"]["status"], "partial")
        self.assertEqual(data["bags"]["status"], "partial")
        self.assertNotIn("private raw error", json.dumps(data))
        self.assertEqual(data["quests"][0]["id"], 123)

    def test_collapsed_and_filtered_lists_are_partial_without_changing_ui(self):
        self.lua.execute('''
            ACTIONS=0
            local function forbidden() ACTIONS=ACTIONS+1; error("must not change game state") end
            C_SkillInfo.ExpandSkillHeader=forbidden
            C_Reputation.ExpandAllFactionHeaders=forbidden
            C_TradeSkillUI.SetShowLearned=forbidden
            C_QuestLog.SetSelectedQuest=forbidden
            C_QuestLog.RequestLoadQuestByID=forbidden
            C_SkillInfo.GetSkillLineInfo=function() return {name="折叠",isHeader=true,isCollapsed=true} end
            C_Reputation.GetFactionDataByIndex=function() return {name="折叠",isHeader=true,isCollapsed=true} end
            ProfessionsFrame={IsShown=function() return true end}
            C_TradeSkillUI.GetFilteredRecipeIDs=C_TradeSkillUI.GetAllRecipeIDs
            C_TradeSkillUI.GetAllRecipeIDs=nil
        ''')
        data = self.collect()
        for category in ("skills", "reputations", "recipes"):
            self.assertEqual(data[category]["status"], "partial")
        self.assertEqual(self.lua.globals().ACTIONS, 0)

    def test_current_trainer_signature_and_cached_lockouts(self):
        self.lua.execute('''
            ClassTrainerFrame={IsShown=function() return true end}
            function GetNumTrainerServices() return 1 end
            function GetTrainerServiceInfo() return "测试技能","available",99,20,"等级 2" end
            function GetTrainerServiceCost() return 100 end
        ''')
        data = self.collect()
        entry = data["trainer"]["entries"][0]
        self.assertEqual(entry["availability"], "available")
        self.assertEqual(entry["requiredLevel"], 20)
        self.assertEqual(entry["rank"], "等级 2")
        self.assertEqual(data["instanceLockouts"]["status"], "partial")

    def test_open_npc_windows_export_data_without_triggering_actions(self):
        self.lua.execute('''
            MerchantFrame={IsShown=function() return true end}
            FlightMapFrame={IsShown=function() return false end, GetMapID=function() return 999 end}
            TaxiFrame={IsShown=function() return true end}
            function GetTaxiMapID() return 12 end
            GossipFrame={IsShown=function() return true end}
            QuestFrame={IsShown=function() return true end}
            function GetMerchantNumItems() return 1 end
            C_MerchantFrame={GetItemInfo=function() return {name="测试商品",price=123,stackCount=1,numAvailable=-1,hasExtendedCost=true} end}
            function GetMerchantItemLink() return "item:987" end
            C_TaxiMap={GetAllTaxiNodes=function(mapID) assert(mapID==12); return {{nodeID=44,name="测试飞行点",state=1}} end}
            C_GossipInfo={GetText=function() return "测试对话" end,
                GetAvailableQuests=function() return {{questID=123,title="测试可接任务"}} end,
                GetActiveQuests=function() return {} end, GetOptions=function() return {{gossipOptionID=10,name="训练"}} end}
            function GetQuestID() return 123 end
            function GetTitleText() return "测试任务" end
            function GetQuestText() return "测试任务正文" end
            function GetObjectiveText() return "测试任务目标" end
            function GetRewardMoney() return 25 end
            function GetRewardXP() return 150 end
            function GetNumQuestRewards() return 1 end
            function GetNumQuestChoices() return 0 end
            function GetQuestItemInfo() return "测试奖励",99,2,1 end
            function GetQuestItemLink() return "item:654" end
        ''')
        data = self.collect()
        self.assertEqual(data["merchant"]["entries"][0]["itemID"], 987)
        self.assertEqual(data["merchant"]["entries"][0]["price"], 123)
        self.assertEqual(data["taxi"]["entries"][0]["nodeID"], 44)
        self.assertEqual(data["taxi"]["mapID"], 12)
        self.assertEqual(data["gossip"]["entries"][0]["questID"], 123)
        self.assertEqual(data["questDialog"]["entries"][0]["count"], 2)
        self.assertEqual(data["questDialog"]["rewardXP"], 150)

    def test_large_payload_stays_compatible_after_python_reserialization(self):
        self.lua.execute('''
            C_QuestLog.GetNumQuestLogEntries=function() return 150 end
            C_QuestLog.GetInfo=function(i) return {questID=i,title=string.rep("任务",500),isHeader=false} end
            C_QuestLog.GetQuestObjectives=function() return {{text=string.rep("进度",500)}} end
            C_QuestLog.GetAllCompletedQuestIDs=function() local ids={} for i=1,10000 do ids[i]=i end return ids end
            ProfessionsFrame={IsShown=function() return true end}
            C_TradeSkillUI.GetAllRecipeIDs=function() local ids={} for i=1,1000 do ids[i]=i end return ids end
            C_TradeSkillUI.GetRecipeInfo=function(id) return {recipeID=id,name=string.rep("材料",200),learned=true} end
        ''')
        data = self.collect()
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertLess(len(serialized.encode("utf-8")), 200000)
        self.assertTrue(data["export"]["omitted"])
        self.assertGreater(data["coverageSummary"]["partial"], 0)
        self.assertEqual(data["coverage"]["recipes"]["count"], len(data["recipes"]["entries"]))
        self.assertEqual(data["questDetails"]["count"], len(data["quests"]))
        build_request("OpenAI", "fixture-model", "规划任务", snapshot=data)

    def test_utf8_bounds_and_combat_refusal_survive_expansion(self):
        self.lua.globals().LONG_TEXT = "中" * 999 + "😀尾"
        shortened = self.lua.eval("ForeverAI.Scalar(LONG_TEXT)")
        self.assertEqual(shortened, "中" * 999)
        self.lua.execute("function InCombatLockdown() return true end")
        data, reason = self.lua.eval("ForeverAI.Collect()")
        self.assertIsNone(data)
        self.assertIn("combat", reason)


if __name__ == "__main__":
    unittest.main()
