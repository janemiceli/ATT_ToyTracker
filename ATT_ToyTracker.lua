local ADDON_NAME = ...
ATT_ToyTrackerDB = ATT_ToyTrackerDB or {}

-- ============================================================
-- Core scan/export
-- ============================================================

local function SafeLower(s) return type(s) == "string" and s:lower() or "" end

local function IsToyNode(node)
    return node and node.itemID and C_ToyBox.GetToyInfo(node.itemID) ~= nil
end

-- Try to pull a "best-effort" location string from an ATT node.
-- ATT data can vary; we gracefully handle missing/unknown fields.
local function GetLocationFromNode(node)
    if not node then return nil end

    local function MapName(mapID)
        if not mapID then return nil end
        local info = C_Map.GetMapInfo(mapID)
        return info and info.name or nil
    end

    local function CoordsToString(x, y, mapID)
        if type(x) ~= "number" or type(y) ~= "number" then return nil end
        local mapName = MapName(mapID)
        if mapName then
            return string.format("%.1f, %.1f — %s (%d)", x, y, mapName, mapID or 0)
        elseif mapID then
            return string.format("%.1f, %.1f — MapID %d", x, y, mapID)
        else
            return string.format("%.1f, %.1f", x, y)
        end
    end

    -- Common patterns in ATT datasets:
    -- node.coord = {x, y, mapID}
    if type(node.coord) == "table" then
        local x, y, mapID = node.coord[1], node.coord[2], node.coord[3]
        local s = CoordsToString(x, y, mapID)
        if s then return s end
    end

    -- node.coords = { {x, y, mapID}, {x, y, mapID}, ... }
    if type(node.coords) == "table" then
        local first = node.coords[1]
        if type(first) == "table" then
            local x, y, mapID = first[1], first[2], first[3]
            local s = CoordsToString(x, y, mapID)
            if s then return s end
        end
    end

    -- Some entries have maps={mapID,...} without coords
    if type(node.maps) == "table" then
        local mapID = node.maps[1]
        if type(mapID) == "number" then
            local mapName = MapName(mapID)
            if mapName then
                return string.format("%s (%d)", mapName, mapID)
            else
                return string.format("MapID %d", mapID)
            end
        end
    end

    return nil
end

local function ScanNode(node, results)
    if not node then return end

    if IsToyNode(node) then
        local itemID = node.itemID
        local owned = PlayerHasToy(itemID)
        local name = node.text

        -- Fallback: try actual toy name from Blizzard API
        if not name then
            local toyName = C_Item.GetItemNameByID(itemID)
            name = toyName or ("ItemID " .. itemID)
        end

        local loc = GetLocationFromNode(node)

        results[itemID] = {
            name = name,
            owned = owned,
            location = loc,
        }
    end

    if node.g then
        for _, child in ipairs(node.g) do
            ScanNode(child, results)
        end
    end
end

local function GetATTRoot()
    -- ATT provides multiple ways internally; this tries a few safe ones.
    if not AllTheThings then return nil end
    if AllTheThings.GetDataCache then
        return AllTheThings:GetDataCache()
    end
    -- Fallback: some versions expose AllTheThings.Data
    if AllTheThings.Data then return AllTheThings.Data end
    return nil
end

local function ScanATTForToys()
    local root = GetATTRoot()
    if not root then
        print("ATT Toy Tracker: ATT not ready yet (try again after it finishes loading).")
        return nil
    end

    local results = {}
    ScanNode(root, results)

    ATT_ToyTrackerDB.lastScan = time()
    ATT_ToyTrackerDB.toys = results

    local count = 0
    for _ in pairs(results) do count = count + 1 end
    print("ATT Toy Tracker: Scan complete. Toys found:", count)

    return results
end

local function BuildCSV(onlyMissing)
    local toys = ATT_ToyTrackerDB.toys
    if not toys then return nil end

    local lines = {}
    table.insert(lines, "itemID,status,name,location")

    for itemID, data in pairs(toys) do
        if not onlyMissing or not data.owned then
            local status = data.owned and "OWNED" or "MISSING"
            local name = data.name or ("ItemID " .. itemID)
            local loc = data.location or ""
            -- %q quotes strings safely for CSV-ish output (double-quotes & escapes)
            table.insert(lines, string.format("%d,%s,%q,%q", itemID, status, name, loc))
        end
    end

    table.sort(lines, function(a, b)
        -- keep header at top
        if a:find("^itemID,") then return true end
        if b:find("^itemID,") then return false end
        return a < b
    end)

    return table.concat(lines, "\n")
end

-- ============================================================
-- UI Panel
-- ============================================================

local UI = {}

local function EnsureUI()
    if UI.frame then return end

    local f = CreateFrame("Frame", "ATT_ToyTrackerFrame", UIParent, "BackdropTemplate")
    f:SetSize(760, 520)
    f:SetPoint("CENTER")
    f:SetMovable(true)
    f:EnableMouse(true)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", f.StartMoving)
    f:SetScript("OnDragStop", f.StopMovingOrSizing)
    f:SetClampedToScreen(true)

    f:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = true, tileSize = 32, edgeSize = 32,
        insets = { left = 8, right = 8, top = 8, bottom = 8 }
    })

    local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", 16, -14)
    title:SetText("ATT Toy Tracker")

    local subtitle = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    subtitle:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -6)
    subtitle:SetText("Scan toys from ATT, export CSV, and view missing toy locations (best-effort).")

    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -6, -6)

    local function MakeButton(text, x, y, onClick)
        local b = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
        b:SetSize(120, 24)
        b:SetPoint("TOPLEFT", 16 + x, -68 + y)
        b:SetText(text)
        b:SetScript("OnClick", onClick)
        return b
    end

    -- Output box label
    local outLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    outLabel:SetPoint("TOPLEFT", 16, -106)
    outLabel:SetText("Export Output (click inside, Ctrl/Cmd+C to copy):")

    -- Scrollable edit box for export text
    local scroll = CreateFrame("ScrollFrame", "ATT_ToyTrackerScroll", f, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 16, -126)
    scroll:SetPoint("BOTTOMLEFT", 16, 16)
    scroll:SetWidth(430)

    local edit = CreateFrame("EditBox", "ATT_ToyTrackerEditBox", scroll)
    edit:SetMultiLine(true)
    edit:SetAutoFocus(false)
    edit:SetFontObject("ChatFontNormal")
    edit:SetWidth(410)
    edit:SetScript("OnEscapePressed", function() edit:ClearFocus() end)
    edit:SetText("Run Scan, then Export to populate this box.")
    scroll:SetScrollChild(edit)

    -- Missing list label
    local missLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    missLabel:SetPoint("TOPLEFT", 470, -106)
    missLabel:SetText("Missing Toys (double-click to copy line):")

    local missScroll = CreateFrame("ScrollFrame", "ATT_ToyTrackerMissingScroll", f, "UIPanelScrollFrameTemplate")
    missScroll:SetPoint("TOPLEFT", 470, -126)
    missScroll:SetPoint("BOTTOMRIGHT", -32, 16)

    local missEdit = CreateFrame("EditBox", "ATT_ToyTrackerMissingEditBox", missScroll)
    missEdit:SetMultiLine(true)
    missEdit:SetAutoFocus(false)
    missEdit:SetFontObject("ChatFontNormal")
    missEdit:SetWidth(240)
    missEdit:SetScript("OnEscapePressed", function() missEdit:ClearFocus() end)
    missEdit:SetText("Run Scan to populate missing toys.")
    missScroll:SetScrollChild(missEdit)

    local function UpdateMissingBox()
        local toys = ATT_ToyTrackerDB.toys
        if not toys then
            missEdit:SetText("No data. Run Scan.")
            return
        end
        local lines = {}
        for itemID, data in pairs(toys) do
            if not data.owned then
                local loc = data.location or "Unknown"
                local name = data.name or ("ItemID " .. itemID)
                table.insert(lines, string.format("%d — %s — %s", itemID, name, loc))
            end
        end
        table.sort(lines)
        if #lines == 0 then
            missEdit:SetText("Nice! No missing toys found (or ATT didn't provide toy data).")
        else
            missEdit:SetText(table.concat(lines, "\n"))
        end
    end

    local function SetOutputText(text)
        edit:SetText(text or "")
        edit:HighlightText(0, 0)
        edit:SetCursorPosition(0)
    end

    MakeButton("Scan", 0, 0, function()
        ScanATTForToys()
        UpdateMissingBox()
    end)

    MakeButton("Export All", 128, 0, function()
        if not ATT_ToyTrackerDB.toys then
            local ok = ScanATTForToys()
            if not ok then return end
        end
        local csv = BuildCSV(false)
        SetOutputText(csv or "")
    end)

    MakeButton("Export Missing", 256, 0, function()
        if not ATT_ToyTrackerDB.toys then
            local ok = ScanATTForToys()
            if not ok then return end
        end
        local csv = BuildCSV(true)
        SetOutputText(csv or "")
    end)

    MakeButton("Clear", 384, 0, function()
        SetOutputText("")
    end)

    -- Store refs
    UI.frame = f
    UI.outputEdit = edit
    UI.missingEdit = missEdit
    UI.updateMissing = UpdateMissingBox
end

local function ToggleUI()
    EnsureUI()
    if UI.frame:IsShown() then
        UI.frame:Hide()
    else
        UI.frame:Show()
        if UI.updateMissing then UI.updateMissing() end
    end
end

-- ============================================================
-- Slash Commands
-- ============================================================

SLASH_ATTTOYTRACKER1 = "/atttoys"
SlashCmdList["ATTTOYTRACKER"] = function(msg)
    msg = SafeLower(msg)

    if msg == "scan" then
        ScanATTForToys()

    elseif msg == "export" then
        if not ATT_ToyTrackerDB.toys then
            local ok = ScanATTForToys()
            if not ok then return end
        end
        local csv = BuildCSV(false)
        if not csv then return end
        print("ATT Toy Tracker: Use /atttoys ui for a copy-friendly export box.")
        -- also print a short header so you can find it if you still want chat output
        print("----- ATT TOY EXPORT (CSV) START -----")
        -- chunked to avoid truncation
        local chunkSize = 240
        for i = 1, #csv, chunkSize do
            print(csv:sub(i, i + chunkSize - 1))
        end
        print("----- ATT TOY EXPORT (CSV) END -----")

    elseif msg == "missing" then
        if not ATT_ToyTrackerDB.toys then
            local ok = ScanATTForToys()
            if not ok then return end
        end
        local csv = BuildCSV(true)
        if not csv then return end
        print("ATT Toy Tracker: Use /atttoys ui for a copy-friendly export box.")
        print("----- ATT MISSING TOYS EXPORT (CSV) START -----")
        local chunkSize = 240
        for i = 1, #csv, chunkSize do
            print(csv:sub(i, i + chunkSize - 1))
        end
        print("----- ATT MISSING TOYS EXPORT (CSV) END -----")

    elseif msg == "ui" or msg == "" then
        ToggleUI()

    else
        print("ATT Toy Tracker commands:")
        print("/atttoys ui        - toggle the UI panel (default)")
        print("/atttoys scan      - scan toy data from ATT")
        print("/atttoys export    - export ALL toys as CSV (chat + UI)")
        print("/atttoys missing   - export ONLY missing toys as CSV (chat + UI)")
    end
end
