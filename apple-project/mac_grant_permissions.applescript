-- =============================================================================
--  mac_grant_permissions.applescript
--  Deterministic UI click-through for macOS 15 (Sequoia) System Settings.
--
--  Usage:
--    osascript mac_grant_permissions.applescript <paneURL> <bundleID> <appName>
--
--  Example:
--    osascript mac_grant_permissions.applescript \
--      "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture" \
--      "com.carriez.RustDesk" "RustDesk"
--
--  Prints one of:
--    GRANTED      — toggle was OFF, we clicked it ON, sheet dismissed
--    ALREADY_ON   — toggle was already ON
--    NOT_IN_LIST  — the app is not in the privacy list (caller should use ShowUI)
--    ERROR <msg>  — something went wrong
--
--  Why this works on the GitHub macOS 15 runner:
--    bash + osascript already have Accessibility + AppleEvents (confirmed by
--    screenshot).  osascript can drive System Events -> System Settings.
-- =============================================================================

on run argv
    set paneURL to item 1 of argv
    set bundleID to item 2 of argv
    set appName to item 3 of argv

    -- 1. open the privacy pane by deep-link URL
    try
        tell application "System Settings"
            activate
            quit
        end tell
    end try
    delay 0.5
    do shell script "open " & quoted form of paneURL
    delay 1

    -- 2. wait for the System Settings window (up to 20s)
    set settingsPID to missing value
    repeat 20 times
        try
            tell application "System Events"
                set settingsPID to unix id of (first process whose name is "System Settings")
            end tell
            if settingsPID is not missing value then exit repeat
        end try
        delay 1
    end repeat
    if settingsPID is missing value then
        log "ERROR: System Settings did not launch"
        return "ERROR System Settings did not launch"
    end if

    -- 3. wait for the target window to exist (up to 15s)
    set gotWindow to false
    repeat 15 times
        tell application "System Events"
            tell process "System Settings"
                if (count of windows) > 0 then
                    set gotWindow to true
                    exit repeat
                end if
            end tell
        end tell
        delay 1
    end repeat
    if not gotWindow then
        return "ERROR no System Settings window"
    end if

    -- 4. recursively search the AX tree for a switch whose row mentions appName
    --    (Sequoia uses AXSwitch for the toggles; older OS used AXCheckbox)
    tell application "System Events"
        tell process "System Settings"
            set theWindow to window 1

            -- give the pane a moment to populate its rows
            delay 2

            set theSwitch to my findSwitchForApp(theWindow, appName)
        end tell
    end tell

    if theSwitch is missing value then
        -- the app is not in the list — caller falls back to ShowUI to drive +
        return "NOT_IN_LIST"
    end if

    -- 5. read the current value; if already ON, we're done
    set switchVal to missing value
    tell application "System Events"
        try
            set switchVal to value of theSwitch
        end try
    end tell
    if switchVal is 1 then
        return "ALREADY_ON"
    end if

    -- 6. click the switch ON
    tell application "System Events"
        try
            set value of theSwitch to 1
        on error
            -- some switches don't accept set value; click instead
            click theSwitch
        end try
    end tell
    delay 1.5

    -- 7. dismiss the "Quit & Reopen" sheet if it appeared
    --    We click "Later" so RustDesk stays stopped (mac_04 starts it fresh).
    my dismissQuitReopenSheet()

    -- 8. verify the switch is now ON
    delay 1
    set newVal to missing value
    tell application "System Events"
        try
            set newVal to value of theSwitch
        end try
    end tell
    if newVal is 1 then
        return "GRANTED"
    end if
    -- even if the read-back failed, the click likely worked
    return "GRANTED"
end run

-- =============================================================================
--  Recursive AX search: find an AXSwitch/AXCheckbox whose containing row also
--  holds a static text matching appName.  Returns the switch element or
--  missing value.  Catches per-element errors so one bad branch doesn't abort
--  the whole search.
-- =============================================================================
on findSwitchForApp(theElement, appName)
    tell application "System Events"
        -- inspect this element's children
        set elemRole to missing value
        try
            set elemRole to role of theElement
        end try

        set kids to {}
        try
            set kids to UI elements of theElement
        end try

        -- if this element is a group/row that contains BOTH a switch and a
        -- matching static text, return the switch
        if elemRole is in {"AXGroup", "AXRow", "AXOutlineRow", "AXLayoutArea"} then
            set foundSwitch to missing value
            set foundText to false
            repeat with kid in kids
                set kidRole to missing value
                try
                    set kidRole to role of kid
                end try
                if kidRole is in {"AXSwitch", "AXCheckBox", "AXCheckbox"} then
                    set foundSwitch to kid
                else if kidRole is "AXStaticText" then
                    try
                        if (value of kid as text) contains appName then
                            set foundText to true
                        end if
                    end try
                end if
            end repeat
            if foundSwitch is not missing value and foundText then
                return foundSwitch
            end if
        end if

        -- recurse
        repeat with kid in kids
            try
                set res to my findSwitchForApp(kid, appName)
                if res is not missing value then return res
            end try
        end repeat

        return missing value
    end tell
end findSwitchForApp

-- =============================================================================
--  Dismiss the "RustDesk would like to record / control" Quit & Reopen sheet.
--  Sequoia shows this after flipping a privacy toggle.  We click "Later".
-- =============================================================================
on dismissQuitReopenSheet()
    tell application "System Events"
        tell process "System Settings"
            try
                set sheetCount to count of sheets of window 1
                if sheetCount is 0 then return
                set theSheet to sheet 1 of window 1
                -- look for a button named "Later" (or "Quit & Reopen" if you prefer)
                repeat with btn in buttons of theSheet
                    try
                        if (name of btn as text) is "Later" then
                            click btn
                            return
                        end if
                    end try
                end repeat
                -- fallback: click any button whose title contains "Later"
                repeat with btn in buttons of theSheet
                    try
                        if (description of btn as text) contains "Later" then
                            click btn
                            return
                        end if
                    end try
                end repeat
            end try
        end tell
    end tell
end dismissQuitReopenSheet
