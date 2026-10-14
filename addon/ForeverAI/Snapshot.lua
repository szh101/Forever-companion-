-- Explicit, read-only Forever 1.60.1 collectors. No global-table dumping, UI
-- selection/filter changes, server queries, background polling or saved data.
local AI = ForeverAI
local read, scalar, field, secret = AI.Read, AI.Scalar, AI.Field, AI.Secret
local MAX_BYTES = 180000 -- leave room below the companion's 200 KB wire limit

local function member(object, key)
    if secret(object) or type(object) ~= "table" then return nil end
    local ok, value = pcall(function() return object[key] end)
    if ok and not secret(value) then return value end
end
local function api(namespace, name) return member(namespace, name) end
local function enum(group, name) return field(member(Enum, group), name) end
local function many(fn, ...)
    if type(fn) ~= "function" then return {}, false end
    local values = {pcall(fn, ...)}
    if values[1] ~= true then return {}, false end
    local out = {}
    for i = 1, 20 do out[i] = scalar(values[i + 1]) end
    return out, true
end
local function pick(object, keys)
    local out = {}
    for _, key in ipairs(keys) do out[key] = field(object, key) end
    return out
end
local function number(value)
    value = scalar(value)
    if type(value) == "number" then return value end
end
local function partial(section, reason)
    section.status = "partial"
    section.notes = section.notes or {}
    for _, note in ipairs(section.notes) do if note == reason then return end end
    section.notes[#section.notes + 1] = reason
end
local function unavailable(section, reason)
    section.status, section.reason = "unavailable", reason
end
local function window(section, frame, hint)
    if not frame or read(member(frame, "IsShown"), frame) ~= true then
        section.status, section.reason = "requires_window", hint
        return false
    end
    return true
end
local function shownFrame(first, second)
    if read(member(first, "IsShown"), first) == true then return first end
    if read(member(second, "IsShown"), second) == true then return second end
end
local function count(section, value, limit)
    local n = number(value)
    if not n or n < 0 or n ~= math.floor(n) then
        unavailable(section, "API count unavailable or restricted")
        return 0
    end
    if n > limit then partial(section, "entry limit; list is not exhaustive") end
    return math.min(n, limit)
end
local function append(section, row)
    -- Section limits bound work and copying without throwing away every category
    -- when one long list is large. Final transport trimming also records omissions.
    local bytes = #AI.Encode(row)
    section._bytes = (section._bytes or 0) + bytes
    if section._bytes > (section._limit or 32000) then
        partial(section, "section size limit; list is not exhaustive")
        section.omitted = (section.omitted or 0) + 1
        return false
    end
    section.entries[#section.entries + 1] = row
    return true
end
local function array(section, values, maximum, visitor)
    if secret(values) or type(values) ~= "table" then
        unavailable(section, "API list unavailable or restricted")
        return
    end
    for i = 1, maximum + 1 do
        local ok, value = pcall(function() return values[i] end)
        if not ok or secret(value) then partial(section, "restricted entry"); return end
        if value == nil then return end
        if i > maximum then partial(section, "entry limit; list is not exhaustive"); return end
        if visitor(value, i) == false then return end
    end
end
local function section(snapshot, key, scope, collect, limit)
    local value = {status = "collected", scope = scope, entries = {}, capturedAt = snapshot.capturedAt,
                   _limit = limit}
    local ok = pcall(collect, value)
    if not ok then
        -- Discard a failed collector, rather than serialize partially trusted data
        -- or an API error containing client text. Other categories still export.
        value = {status = "unavailable", reason = "collector failed or data restricted",
                 scope = scope, entries = {}, capturedAt = snapshot.capturedAt}
    end
    value._bytes, value._limit = nil, nil
    snapshot[key] = value
    return value
end

local function item(link, id)
    local out = {id = number(id), link = scalar(link)}
    if type(out.link) == "string" then out.id = out.id or tonumber(out.link:match("item:(%d+)")) end
    if not out.id and not out.link then return out end
    local values = many(api(C_Item, "GetItemInfo") or GetItemInfo, out.link or out.id)
    out.name, out.quality, out.itemLevel, out.requiredLevel = values[1], values[3], values[4], values[5]
    out.type, out.subType, out.equipLocation, out.sellPriceCopper = values[6], values[7], values[9], values[11]
    out.detailsCached = values[1] ~= nil
    return out
end

local function profile(snapshot, s)
    local p = snapshot.player
    p.name, p.realm = scalar(read(UnitName, "player")), scalar(read(GetRealmName))
    p.race = scalar(read(UnitRace, "player"))
    p.classToken = many(UnitClass, "player")[2]
    p.sex = scalar(read(UnitSex, "player"))
    p.xp, p.maxXP, p.restedXP = scalar(read(UnitXP, "player")), scalar(read(UnitXPMax, "player")), scalar(read(GetXPExhaustion))
    p.moneyCopper, p.bindLocation = scalar(read(GetMoney)), scalar(read(GetBindLocation))
    for _, pair in ipairs({{"health", UnitHealth}, {"maxHealth", UnitHealthMax},
        {"power", UnitPower}, {"maxPower", UnitPowerMax}, {"powerType", UnitPowerType},
        {"dead", UnitIsDead}, {"ghost", UnitIsGhost}, {"resting", IsResting},
        {"mounted", IsMounted}, {"swimming", IsSwimming}}) do
        p[pair[1]] = scalar(read(pair[2], "player"))
    end
    s.data = p
    s.scope = "own character, out of combat; nil fields are unknown, not zero"
end

local function stats(s)
    if type(UnitStat) ~= "function" then unavailable(s, "character stats API unavailable"); return end
    for index, name in ipairs({"strength", "agility", "stamina", "intellect", "spirit"}) do
        local v = many(UnitStat, "player", index)
        if v[1] then append(s, {stat = name, base = v[1], effective = v[2], positive = v[3], negative = v[4]})
        else partial(s, "one or more stats unavailable or restricted") end
    end
    local armor = many(UnitArmor, "player")
    s.armor = {base = armor[1], effective = armor[2], total = armor[3]}
    local ap = many(UnitAttackPower, "player")
    s.attackPower = {base = ap[1], positive = ap[2], negative = ap[3]}
    s.critPercent, s.dodgePercent = scalar(read(GetCritChance)), scalar(read(GetDodgeChance))
    s.parryPercent, s.blockPercent = scalar(read(GetParryChance)), scalar(read(GetBlockChance))
    s.resistances = {}
    for school = 0, 6 do
        local v = many(UnitResistance, "player", school)
        if v[1] then s.resistances[#s.resistances + 1] = {school = school, base = v[1], total = v[2]} end
    end
end

local function equipment(snapshot, s)
    for _, equipped in ipairs(snapshot.equipment) do
        local out = item(equipped.link, equipped.id)
        out.slot = equipped.slot
        local v = many(GetInventoryItemDurability, out.slot)
        out.durability, out.maxDurability = v[1], v[2]
        if not out.detailsCached then partial(s, "item details not cached; IDs and links remain usable") end
        append(s, out)
    end
end

local function container(s, bagID, label)
    local getSlots = api(C_Container, "GetContainerNumSlots")
    if type(getSlots) ~= "function" then unavailable(s, "container API unavailable"); return end
    local raw = read(getSlots, bagID)
    local slots = number(raw)
    if not slots or slots < 0 then partial(s, "container slots unavailable"); return end
    local free = many(api(C_Container, "GetContainerNumFreeSlots"), bagID)
    s.containers = s.containers or {}
    s.containers[#s.containers + 1] = {id = bagID, name = scalar(read(api(C_Container, "GetBagName"), bagID)),
        kind = label, slots = slots, freeSlots = free[1], family = free[2]}
    if slots > 200 then partial(s, "container slot limit") end
    for slot = 1, math.min(slots, 200) do
        local info = read(api(C_Container, "GetContainerItemInfo"), bagID, slot)
        if type(info) == "table" and not secret(info) then
            local out = {bag = bagID, slot = slot, id = field(info, "itemID"), name = field(info, "itemName"),
                         count = field(info, "stackCount"), quality = field(info, "quality"), bound = field(info, "isBound")}
            if not out.id then partial(s, "item identity unavailable")
            elseif not append(s, out) then return end
        elseif scalar(read(api(C_Container, "HasContainerItem"), bagID, slot)) ~= false then
            partial(s, "slot not confirmed empty; cached item details unavailable")
        end
    end
end

local function bags(s)
    local last = math.min(number(NUM_BAG_SLOTS) or 4, 10)
    for bag = 0, last do container(s, bag, "carried") end
    local reagent = number(enum("BagIndex", "ReagentBag"))
    if reagent and (reagent < 0 or reagent > last) then container(s, reagent, "reagent") end
end

local function bank(s)
    if not window(s, BankFrame, "open your bank and export again; closed bank is unknown, not empty") then return end
    local getIDs = api(C_Bank, "FetchPurchasedBankTabIDs")
    if type(getIDs) == "function" then
        for _, label in ipairs({"Character", "Account"}) do
            local bankType = enum("BankType", label)
            if bankType then
                if read(api(C_Bank, "CanViewBank"), bankType) == true then
                    array(s, read(getIDs, bankType), 20, function(id)
                        id = number(id)
                        if id then container(s, id, label) else partial(s, "bank tab unavailable") end
                    end)
                else partial(s, label .. " bank not viewable") end
            end
        end
    else
        -- Older clients only; Forever uses purchased bank-tab BagIndex values.
        local main = number(BANK_CONTAINER)
        if not main then unavailable(s, "bank tab API unavailable"); return end
        container(s, main, "character")
        local first, total = number(NUM_BAG_SLOTS) or 4, number(NUM_BANKBAGSLOTS) or 0
        for id = first + 1, first + math.min(total, 12) do container(s, id, "character") end
    end
end

local function quests(snapshot, s)
    s.scope = "quest log currently exposed by the client, not all possible quests"
    for _, quest in ipairs(snapshot.quests) do
        local id = quest.id
        quest.failed = scalar(read(api(C_QuestLog, "IsFailed"), id))
        quest.repeatable = scalar(read(api(C_QuestLog, "IsRepeatableQuest"), id))
        quest.suggestedGroupSize = scalar(read(api(C_QuestLog, "GetSuggestedGroupSize"), id))
        local nextPoint = many(api(C_QuestLog, "GetNextWaypoint"), id)
        if nextPoint[1] then quest.nextWaypoint = {mapID = nextPoint[1], x = nextPoint[2], y = nextPoint[3]} end
        if quest.objectivesStatus ~= "collected" then partial(s, "some objectives unavailable") end
    end
    s.count = #snapshot.quests
    if snapshot.questStatus ~= "collected" then partial(s, snapshot.questStatus) end
    local selected = number(read(api(C_QuestLog, "GetSelectedQuest")))
    if selected then
        local text = many(GetQuestLogQuestText, selected)
        s.selectedQuest = {id = selected, description = text[1], objectivesText = text[2]}
    end
end

local function completed(s)
    array(s, read(api(C_QuestLog, "GetAllCompletedQuestIDs")), 10000, function(value)
        local id = number(value)
        if id then return append(s, id) end
        partial(s, "invalid or restricted quest ID")
    end)
end

local function skills(s)
    local n = count(s, read(api(C_SkillInfo, "GetNumSkillLines")), 250)
    for i = 1, n do
        local info = read(api(C_SkillInfo, "GetSkillLineInfo"), i)
        local out = pick(info, {"skillID", "name", "isHeader", "isCollapsed", "rank", "maxRank", "modifier", "tempPoints", "minLevel"})
        if out.isCollapsed then partial(s, "collapsed skill headers; expand in game and export again") end
        if out.name then append(s, out) else partial(s, "skill unavailable") end
    end
end

local function professions(s)
    if type(GetProfessions) ~= "function" then unavailable(s, "profession API unavailable"); return end
    local ids, ok = many(GetProfessions)
    if not ok then unavailable(s, "profession list failed"); return end
    for i = 1, 7 do
        local index = number(ids[i])
        if index then
            local v = many(GetProfessionInfo, index)
            if v[1] then append(s, {name = v[1], rank = v[3], maxRank = v[4], skillLineID = v[7], rankModifier = v[8]})
            else partial(s, "profession info unavailable") end
        end
    end
end

local function recipes(snapshot, s)
    if not window(s, shownFrame(ProfessionsFrame, TradeSkillFrame), "open your own profession; only the currently loaded profession can be read") then return end
    local ownershipKnown = true
    for _, fn in ipairs({"IsTradeSkillLinked", "IsTradeSkillGuild", "IsTradeSkillGuildMember", "IsNPCCrafting"}) do
        local other = read(api(C_TradeSkillUI, fn))
        if other == true then
            unavailable(s, "viewing another crafter or NPC, not your learned recipes"); return
        end
        if other ~= false then ownershipKnown = false end
    end
    s.profession = pick(read(api(C_TradeSkillUI, "GetBaseProfessionInfo")),
        {"professionID", "professionName", "skillLevel", "maxSkillLevel", "parentProfessionID"})
    local ownProfession = false
    for _, profession in ipairs(snapshot.professions.entries) do
        if profession.skillLineID and (profession.skillLineID == s.profession.professionID or
            profession.skillLineID == s.profession.parentProfessionID) then ownProfession = true end
    end
    s.ownership = ownershipKnown and ownProfession and "player" or "unverified-current-view"
    if s.ownership ~= "player" then partial(s, "ownership unverified; do not treat learned flags as your character's recipe history") end
    local ids = read(api(C_TradeSkillUI, "GetAllRecipeIDs"))
    if not ids then
        ids = read(api(C_TradeSkillUI, "GetFilteredRecipeIDs"))
        partial(s, "filtered recipe list; clear filters in game to see more")
    end
    array(s, ids, 1000, function(value)
        local id = number(value)
        if not id then partial(s, "recipe ID unavailable"); return end
        local info = read(api(C_TradeSkillUI, "GetRecipeInfo"), id)
        local out = pick(info, {"recipeID", "name", "learned", "categoryID", "relativeDifficulty", "maxTrivialLevel", "sourceType", "disabledReason"})
        if not out.name then partial(s, "recipe data not loaded"); return end
        out.recipeID = id
        local schematic = read(api(C_TradeSkillUI, "GetRecipeSchematic"), id, false)
        out.outputItemID, out.quantityMin, out.quantityMax = field(schematic, "outputItemID"), field(schematic, "quantityMin"), field(schematic, "quantityMax")
        out.reagents = {}
        local slots = member(schematic, "reagentSlotSchematics")
        if type(slots) == "table" then
            for i = 1, 20 do
                local slot = member(slots, i)
                if not slot then break end
                local reagent = {required = field(slot, "required"), quantity = field(slot, "quantityRequired"), alternatives = {}}
                local alternatives = member(slot, "reagents")
                for j = 1, 8 do
                    local option = member(alternatives, j)
                    if not option then break end
                    reagent.alternatives[#reagent.alternatives + 1] = pick(option, {"itemID", "currencyID"})
                end
                out.reagents[#out.reagents + 1] = reagent
            end
        else out.reagentsStatus = "unavailable"; partial(s, "some recipe materials unavailable") end
        return append(s, out)
    end)
end

local function spellbook(s)
    local n = count(s, read(api(C_SpellBook, "GetNumSpellBookSkillLines")), 30)
    local bankID = enum("SpellBookSpellBank", "Player")
    if bankID == nil then unavailable(s, "spell bank enum unavailable"); return end
    for i = 1, n do
        local line = read(api(C_SpellBook, "GetSpellBookSkillLineInfo"), i)
        local offset, total = number(field(line, "itemIndexOffset")), number(field(line, "numSpellBookItems"))
        if offset and total and total >= 0 then
            if total > 500 then partial(s, "spell count limit") end
            for slot = offset + 1, offset + math.min(total, 500) do
                local out = pick(read(api(C_SpellBook, "GetSpellBookItemInfo"), slot, bankID),
                    {"spellID", "actionID", "itemType", "name", "subName", "isPassive", "isOffSpec"})
                out.skillLine = field(line, "name")
                if out.name then if not append(s, out) then return end
                else partial(s, "spell not loaded or restricted") end
            end
        else partial(s, "spell skill line unavailable") end
    end
end

local function talents(s)
    local configID = number(read(api(C_ClassTalents, "GetActiveConfigID")))
    if not configID then unavailable(s, "active talent config unavailable or not unlocked"); return end
    s.configID = configID
    local info = read(api(C_Traits, "GetConfigInfo"), configID)
    s.name = field(info, "name")
    array(s, member(info, "treeIDs"), 8, function(treeID)
        treeID = number(treeID)
        if not treeID then partial(s, "tree ID unavailable"); return end
        array(s, read(api(C_Traits, "GetTreeNodes"), treeID), 500, function(nodeID)
            nodeID = number(nodeID)
            if not nodeID then partial(s, "node ID unavailable"); return end
            local node = read(api(C_Traits, "GetNodeInfo"), configID, nodeID)
            local rank = number(field(node, "activeRank"))
            if rank == nil then partial(s, "talent node unavailable"); return end
            if rank > 0 then
                local active = member(node, "activeEntry")
                local entryID = number(field(active, "entryID"))
                local entry = entryID and read(api(C_Traits, "GetEntryInfo"), configID, entryID)
                local defID = number(field(entry, "definitionID"))
                local definition = defID and read(api(C_Traits, "GetDefinitionInfo"), defID)
                local spellID = number(field(definition, "spellID"))
                local spell = spellID and read(api(C_Spell, "GetSpellInfo"), spellID)
                return append(s, {treeID = treeID, nodeID = nodeID, activeRank = rank,
                    currentRank = field(node, "currentRank"), entryID = entryID, spellID = spellID,
                    name = field(definition, "overrideName") or field(spell, "name")})
            end
        end)
    end)
end

local function reputations(s)
    local n = count(s, read(api(C_Reputation, "GetNumFactions")), 400)
    for i = 1, n do
        local out = pick(read(api(C_Reputation, "GetFactionDataByIndex"), i),
            {"factionID", "name", "reaction", "currentReactionThreshold", "nextReactionThreshold", "currentStanding", "isHeader", "isCollapsed", "atWarWith", "isAccountWide"})
        if out.isCollapsed then partial(s, "collapsed reputation headers; expand in game and export again") end
        if out.name then if not append(s, out) then return end else partial(s, "faction unavailable") end
    end
end
local function currencies(s)
    local n = count(s, read(api(C_CurrencyInfo, "GetCurrencyListSize")), 300)
    for i = 1, n do
        local out = pick(read(api(C_CurrencyInfo, "GetCurrencyListInfo"), i),
            {"name", "quantity", "isHeader", "isHeaderExpanded", "isTypeUnused", "maxQuantity", "totalEarned"})
        out.link = scalar(read(api(C_CurrencyInfo, "GetCurrencyListLink"), i))
        if out.isHeader and out.isHeaderExpanded == false then partial(s, "collapsed currency headers") end
        if out.name then if not append(s, out) then return end else partial(s, "currency unavailable") end
    end
end

local function unitSummary(unit)
    if read(UnitExists, unit) ~= true then return nil end
    return {name = scalar(read(UnitName, unit)), level = scalar(read(UnitLevel, unit)),
            class = scalar(read(UnitClass, unit)), race = scalar(read(UnitRace, unit)),
            isPlayer = scalar(read(UnitIsPlayer, unit)), role = scalar(read(UnitGroupRolesAssigned, unit)),
            dead = scalar(read(UnitIsDeadOrGhost, unit))}
end
local function context(snapshot, s)
    s.subZone, s.bindLocation = scalar(read(GetSubZoneText)), scalar(read(GetBindLocation))
    s.mapID, s.x, s.y = snapshot.mapID, snapshot.x, snapshot.y
    local v = many(GetInstanceInfo)
    s.instance = {name = v[1], type = v[2], difficultyID = v[3], difficultyName = v[4],
                  maxPlayers = v[5], instanceID = v[8]}
    if not snapshot.mapID then partial(s, "map location unavailable") end
end
local function target(snapshot, s)
    local exists = read(UnitExists, "target")
    if exists == false then s.status = "not_applicable"; s.reason = "no target"; return end
    s.data = unitSummary("target")
    if not s.data then unavailable(s, "target summary unavailable"); return end
    s.data.classification = scalar(read(UnitClassification, "target"))
    s.data.faction = scalar(read(UnitFactionGroup, "target"))
    s.inspectionStatus, s.inspectedAt = snapshot.inspectionStatus, snapshot.inspectedAt
end
local function group(s)
    if read(IsInGroup) == false then s.status = "not_applicable"; s.reason = "not grouped"; return end
    local raid = read(IsInRaid) == true
    local total = read(raid and GetNumGroupMembers or GetNumSubgroupMembers)
    for i = 1, count(s, total, 40) do
        local row = unitSummary((raid and "raid" or "party") .. i)
        if row then append(s, row) else partial(s, "group member unavailable") end
    end
    s.raid = raid
end
local function pet(s)
    if read(UnitExists, "pet") == false then s.status = "not_applicable"; s.reason = "no active pet"; return end
    s.data = unitSummary("pet")
    if not s.data then unavailable(s, "pet info unavailable"); return end
    s.data.family = scalar(read(UnitCreatureFamily, "pet"))
    local exp = many(GetPetExperience)
    s.data.xp, s.data.maxXP = exp[1], exp[2]
    local points = many(api(C_PetInfo, "GetPetTrainingPoints"))
    s.data.trainingPoints, s.data.spentTrainingPoints = points[1], points[2]
    s.data.happiness = scalar(read(api(C_PetInfo, "GetPetHappiness")))
    s.data.loyalty = scalar(read(api(C_PetInfo, "GetPetLoyalty")))
end

local function merchant(s)
    if not window(s, MerchantFrame, "talk to a merchant and export while its window is open") then return end
    for i = 1, count(s, read(GetMerchantNumItems), 250) do
        local out = pick(read(api(C_MerchantFrame, "GetItemInfo"), i),
            {"name", "price", "stackCount", "numAvailable", "isPurchasable", "isUsable", "hasExtendedCost", "currencyID", "spellID"})
        out.link = scalar(read(GetMerchantItemLink, i))
        if out.link then out.itemID = tonumber(out.link:match("item:(%d+)")) end
        if out.name then if not append(s, out) then return end else partial(s, "merchant item unavailable") end
    end
    s.priceUnit = "copper; extended currencies are separate"
end
local function trainer(s)
    if not window(s, ClassTrainerFrame, "talk to a trainer and export while its window is open") then return end
    partial(s, "only current trainer and current filters, not all learnable skills")
    for i = 1, count(s, read(GetNumTrainerServices), 250) do
        local v = many(GetTrainerServiceInfo, i)
        if v[1] then
            if not append(s, {name = v[1], rank = v[5], availability = v[2],
                costCopper = scalar(read(GetTrainerServiceCost, i)), requiredLevel = v[4]}) then return end
        else partial(s, "trainer service unavailable") end
    end
end
local function taxi(snapshot, s)
    local frame = shownFrame(FlightMapFrame, TaxiFrame)
    if not window(s, frame, "open a flight master map and export; routes elsewhere are unknown") then return end
    -- The flight map is often a continent, not the player's current zone map.
    local mapID = number(read(member(frame, "GetMapID"), frame)) or number(read(GetTaxiMapID))
    if not mapID then unavailable(s, "flight map ID unavailable"); return end
    s.mapID = mapID
    array(s, read(api(C_TaxiMap, "GetAllTaxiNodes"), mapID), 400, function(info)
        local row = pick(info, {"nodeID", "name", "state", "type", "faction", "mapID"})
        if row.nodeID then return append(s, row) end
        partial(s, "flight node unavailable")
    end)
end
local function gossip(s)
    if not window(s, GossipFrame, "open an NPC conversation and export") then return end
    s.text = scalar(read(api(C_GossipInfo, "GetText")))
    for _, kind in ipairs({"GetAvailableQuests", "GetActiveQuests", "GetOptions"}) do
        local values = read(api(C_GossipInfo, kind))
        if values then
            array(s, values, 100, function(info)
                local out = pick(info, {"questID", "title", "isComplete", "gossipOptionID", "name"})
                out.kind = kind
                return append(s, out)
            end)
        else partial(s, "some NPC choices unavailable") end
    end
end
local function questDialog(s)
    if not window(s, QuestFrame, "open a quest NPC dialog and export") then return end
    s.questID, s.title = scalar(read(GetQuestID)), scalar(read(GetTitleText))
    s.description, s.objectives = scalar(read(GetQuestText)), scalar(read(GetObjectiveText))
    s.rewardMoneyCopper, s.rewardXP = scalar(read(GetRewardMoney)), scalar(read(GetRewardXP))
    for _, kind in ipairs({"reward", "choice"}) do
        local total = read(kind == "reward" and GetNumQuestRewards or GetNumQuestChoices)
        for i = 1, count(s, total, 20) do
            local v = many(GetQuestItemInfo, kind, i)
            if v[1] then append(s, {kind = kind, name = v[1], count = v[3], quality = v[4],
                                   link = scalar(read(GetQuestItemLink, kind, i))}) end
        end
    end
end

local function mounts(s)
    array(s, read(api(C_MountJournal, "GetMountIDs")), 3000, function(value)
        local id = number(value)
        if not id then partial(s, "mount ID unavailable"); return end
        local v = many(api(C_MountJournal, "GetMountInfoByID"), id)
        if v[11] == true then
            return append(s, {id = id, name = v[1], spellID = v[2], usable = v[5], active = v[4]})
        elseif v[11] ~= false then partial(s, "mount ownership unavailable") end
    end)
end
local function collectionPets(s)
    array(s, read(api(C_PetJournal, "GetOwnedPetIDs")), 2000, function(id)
        id = scalar(id)
        if type(id) ~= "string" then partial(s, "pet identity unavailable"); return end
        local row = pick(read(api(C_PetJournal, "GetPetInfoTableByPetID"), id),
            {"speciesID", "name", "petLevel", "xp", "maxXP", "petType", "canBattle"})
        -- The owned pet GUID is only used to query this entry; it is not exported.
        if row.speciesID then return append(s, row) end
        partial(s, "pet collection info unavailable")
    end)
end
local function achievements(s)
    s.totalPoints = scalar(read(GetTotalAchievementPoints))
    local visited = 0
    array(s, read(GetCategoryList), 300, function(categoryID)
        categoryID = number(categoryID)
        if not categoryID then partial(s, "achievement category unavailable"); return end
        local total = count(s, read(GetCategoryNumAchievements, categoryID), 1000)
        for i = 1, total do
            visited = visited + 1
            if visited > 6000 then partial(s, "achievement scan limit"); return false end
            local v = many(GetAchievementInfo, categoryID, i)
            if v[4] == true then
                if not append(s, {id = v[1], name = v[2], points = v[3], month = v[5], day = v[6], year = v[7],
                    earnedByThisCharacter = v[13]}) then return false end
            elseif v[4] ~= false then partial(s, "achievement completion unavailable") end
        end
    end)
    s.inspectedCount = visited
end
local function lockouts(s)
    partial(s, "cached lockouts only; no server refresh requested; empty is not proof of no lockouts")
    for i = 1, count(s, read(GetNumSavedInstances), 100) do
        local v = many(GetSavedInstanceInfo, i)
        if v[1] then append(s, {name = v[1], resetSeconds = v[3], difficultyID = v[4], locked = v[5],
            extended = v[6], isRaid = v[8], maxPlayers = v[9], difficultyName = v[10], encounters = v[11], progress = v[12]})
        else partial(s, "lockout entry unavailable") end
    end
end

local function transportSize(snapshot)
    local encoded = AI.Encode(snapshot)
    -- Existing companions re-serialize with Python's default separator spaces
    -- before validating again. Count even separators inside strings: a safe
    -- upper bound prevents an import that only fails when the user sends.
    local _, separators = encoded:gsub("[,:]", "")
    return #encoded + separators
end
local function fit(snapshot)
    -- No oversized payloads silently rejected by existing companion builds. Keep
    -- every category's coverage while reducing only explicit list tails.
    for _ = 1, 120 do
        if transportSize(snapshot) <= MAX_BYTES then return end
        local rows, owner, size
        for key, value in pairs(snapshot) do
            local candidates = type(value) == "table" and value.entries
            if key == "quests" or key == "equipment" or key == "inspectedEquipment" then candidates = value end
            if candidates and #candidates > 0 then
                local bytes = #AI.Encode(candidates)
                if not size or bytes > size then rows, owner, size = candidates, key, bytes end
            end
        end
        if not rows then return end
        local removed = math.max(1, math.ceil(#rows / 5))
        for _ = 1, removed do table.remove(rows) end
        snapshot.export.omitted[owner] = (snapshot.export.omitted[owner] or 0) + removed
        if owner == "quests" then
            snapshot.questStatus = "partial: export size limit"
            snapshot.omittedQuests = snapshot.omittedQuests + removed
            snapshot.questDetails.count = #rows
            partial(snapshot.questDetails, "export size limit; some quests omitted")
        elseif type(snapshot[owner].status) == "string" then
            partial(snapshot[owner], "total export size limit; list is not exhaustive")
        end
    end
end

function AI.Extend(snapshot)
    snapshot.addonVersion = "0.3.0"
    snapshot.export = {mode = "manual out-of-combat snapshot", completeGameState = false,
        maxBytes = MAX_BYTES, omitted = {},
        semantics = "Missing, unavailable, restricted or omitted is unknown, never empty/zero/unlearned. Collected means returned fields only. Window-scoped lists cover the open window only. No live synchronization.",
        excluded = {"protected/secret data", "combat telemetry", "chat and private messages", "mail content", "friend and guild rosters", "other characters not loaded", "worldwide loot/recipe database", "auction scans"}}
    section(snapshot, "character", "own character", function(s) profile(snapshot, s) end, 6000)
    -- player already carries the shared profile; do not duplicate it in the wire format.
    snapshot.character.data = nil
    section(snapshot, "characterStats", "out-of-combat character sheet", stats, 10000)
    section(snapshot, "location", "current location and instance", function(s) context(snapshot, s) end)
    section(snapshot, "equipmentDetails", "equipped items and cached item details", function(s) equipment(snapshot, s) end, 12000)
    section(snapshot, "bags", "carried bags", bags, 32000)
    section(snapshot, "bank", "currently viewable bank tabs, only while bank is open", bank, 32000)
    section(snapshot, "questDetails", "active quests", function(s) quests(snapshot, s) end)
    section(snapshot, "completedQuests", "completed quest IDs returned by this client", completed, 30000)
    section(snapshot, "skills", "currently exposed skill lines", skills, 14000)
    section(snapshot, "professions", "own profession ranks", professions, 4000)
    section(snapshot, "recipes", "currently open profession only; learned flag belongs to that view", function(s) recipes(snapshot, s) end, 48000)
    section(snapshot, "spellbook", "player spellbook; no runtime cooldowns", spellbook, 32000)
    section(snapshot, "talents", "active talent configuration and active ranks", talents, 20000)
    section(snapshot, "reputations", "currently exposed reputation rows", reputations, 20000)
    section(snapshot, "currencies", "currently exposed currency rows", currencies, 12000)
    section(snapshot, "target", "currently selected unit and manually inspected equipment", function(s) target(snapshot, s) end)
    section(snapshot, "group", "current party/raid composition; no combat telemetry", group, 12000)
    section(snapshot, "pet", "currently active pet only", pet)
    section(snapshot, "merchant", "current merchant offerings", merchant, 20000)
    section(snapshot, "trainer", "current trainer list", trainer, 16000)
    section(snapshot, "taxi", "current flight master nodes", function(s) taxi(snapshot, s) end, 16000)
    section(snapshot, "gossip", "current NPC conversation", gossip, 12000)
    section(snapshot, "questDialog", "current NPC quest dialog", questDialog, 12000)
    section(snapshot, "mounts", "collected mounts reported by the journal", mounts, 20000)
    section(snapshot, "collectionPets", "owned journal pets, not just the active pet", collectionPets, 16000)
    section(snapshot, "achievements", "completed achievements only, not all criteria or guild achievements", achievements, 24000)
    section(snapshot, "instanceLockouts", "locally cached dungeon and raid lockouts", lockouts, 12000)
    for _ = 1, 3 do
        fit(snapshot)
        snapshot.coverage, snapshot.coverageSummary = {}, {collected = 0, partial = 0, unavailable = 0}
        for key, value in pairs(snapshot) do
            if type(value) == "table" and type(value.status) == "string" then
                snapshot.coverage[key] = {status = value.status, reason = value.reason, notes = value.notes, count = value.count or #value.entries}
                if value.status == "collected" then snapshot.coverageSummary.collected = snapshot.coverageSummary.collected + 1
                elseif value.status == "partial" then snapshot.coverageSummary.partial = snapshot.coverageSummary.partial + 1
                else snapshot.coverageSummary.unavailable = snapshot.coverageSummary.unavailable + 1 end
            end
        end
        if transportSize(snapshot) <= MAX_BYTES then break end
    end
end
