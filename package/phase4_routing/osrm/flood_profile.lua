-- ============================================================
-- flood_profile.lua — Custom OSRM car profile with flood penalties
--
-- Extends the default car profile to apply dynamic weight
-- penalties on road segments affected by flooding.
--
-- Penalty data is read from a CSV side-file that the road_risk
-- updater exports periodically.  Format:
--   way_id,weight_multiplier
--   123456789,5.0
--   987654321,inf    (road closed)
-- ============================================================

api_version = 4

-- Import the base car profile
local car = require("car")

function setup()
    local profile = car.setup()

    profile.properties.weight_name = "flood_aware"

    -- Load flood penalty data from CSV
    local penalties = {}
    local penalty_file = os.getenv("FLOOD_PENALTY_CSV") or "/opt/osrm/flood_penalties.csv"
    local f = io.open(penalty_file, "r")
    if f then
        for line in f:lines() do
            local way_id, multiplier = line:match("(%d+),(.*)")
            if way_id and multiplier then
                if multiplier == "inf" then
                    penalties[tonumber(way_id)] = math.huge
                else
                    penalties[tonumber(way_id)] = tonumber(multiplier) or 1.0
                end
            end
        end
        f:close()
        io.stderr:write("[FloodProfile] Loaded " .. #penalties .. " flood penalties\n")
    else
        io.stderr:write("[FloodProfile] No penalty file found at " .. penalty_file .. "\n")
    end

    profile.flood_penalties = penalties
    return profile
end

function process_way(profile, way, result, relations)
    -- Run the base car profile first
    car.process_way(profile, way, result, relations)

    -- Apply flood penalty if this way has one
    local penalty = profile.flood_penalties[way:id()]
    if penalty then
        if penalty == math.huge then
            -- Road is closed
            result.forward_speed = 0
            result.backward_speed = 0
            result.forward_rate = 0
            result.backward_rate = 0
        else
            -- Apply weight multiplier (reduce speed proportionally)
            result.forward_speed = result.forward_speed / penalty
            result.backward_speed = result.backward_speed / penalty
        end
    end
end

function process_node(profile, node, result, relations)
    car.process_node(profile, node, result, relations)
end

function process_turn(profile, turn)
    car.process_turn(profile, turn)
end
