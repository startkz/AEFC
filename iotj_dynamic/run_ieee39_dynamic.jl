#!/usr/bin/env julia
# IEEE 39-bus transient dynamic experiment for IoT-J R1.
using PowerDynamics
using PowerDynamics.Library
using ModelingToolkitBase
using NetworkDynamics
using NetworkDynamics: @cached_component
using ModelingToolkitStandardLibrary.Blocks: RealInput, RealOutput
using OrdinaryDiffEqRosenbrock
using OrdinaryDiffEqNonlinearSolve
using SciMLBase
using CSV
using DataFrames
using JSON

# The custom component is defined in Main (unlike PowerDynamics.Library),
# so declare the independent variable in this module before @cached_component.
@variables t
# The component is built in Main, where PowerDynamics.Library's internal Dt
# is not in scope. Bind the same time derivative operator explicitly.
Dt = Differential(t)

# Preserve the IEEE39 TGOV1 data and add explicit continuous valve slew limits.
@cached_component function TGOV1RateLimited(; name, ω_ref_input=false, p_ref_input=false)
    @named ω_meas = RealInput()
    @named τ_m = RealOutput()
    systems = [ω_meas, τ_m]
    params = @parameters begin
        V_min
        V_max
        R
        T1
        T2
        T3
        DT
        Ropen=0.10
        Rclose=0.10
    end
    vars = @variables begin
        ref_sig(t)
        xg1(t), [guess=1]
        xg2(t), [guess=0]
        Δω(t)
    end
    if ω_ref_input
        @named ω_ref = RealInput()
        push!(systems, ω_ref)
        _ω_ref = ω_ref.u
    else
        @parameters ω_ref=1
        push!(params, ω_ref)
        _ω_ref = ω_ref
    end
    if p_ref_input
        @named p_ref = RealInput()
        push!(systems, p_ref)
        _p_ref = p_ref.u
    else
        @parameters p_ref [guess=1]
        push!(params, p_ref)
        _p_ref = p_ref
    end
    eqs = [
        Δω ~ ω_meas.u - _ω_ref,
        ref_sig ~ 1/R * (_p_ref - Δω),
        Dt(xg1) ~ ifelse(
            ((xg1 > V_max) & (ref_sig > xg1)) | ((xg1 < V_min) & (ref_sig < xg1)),
            0.0,
            max(min((ref_sig - xg1) / T1, Ropen), -Rclose)
        ),
        T3 * Dt(xg2) ~ xg1 + T2 * Dt(xg1) - xg2,
        τ_m.u * ω_meas.u ~ xg2 - DT * Δω
    ]
    System(eqs, t, vars, params; name, systems)
end

function parse_arg(name, default)
    i = findfirst(==(name), ARGS)
    i === nothing && return default
    i < length(ARGS) || error("Missing value for $name")
    return ARGS[i + 1]
end

scenario = parse_arg("--scenario", "rate_limited")
scenario in ("hold", "rate_limited", "step") || error("Invalid scenario")
outdir = parse_arg("--out", "results/iotj_dynamic/" * scenario)
mkpath(outdir)

# Use the maintained IEEE39 topology and dynamic component data shipped with
# the pinned PowerDynamics.jl revision. Replace only the TGOV1 constructor.
example = joinpath(pkgdir(PowerDynamics), "docs", "examples", "ieee39_part1.jl")
source = replace(read(example, String), "TGOV1(" => "TGOV1RateLimited(")
include_string(Main, source, "ieee39_part1_rate_limited.jl")

formula = @initformula :ZIPLoad₊Vset = sqrt(:busbar₊u_r^2 + :busbar₊u_i^2)
set_initformula!(nw[VIndex(31)], formula)
set_initformula!(nw[VIndex(39)], formula)
s0 = initialize_from_pf!(nw; verbose=false)
check_base_consistency(s0)

events = NamedTuple[]
fault_time, trip_time = 0.10, 0.20
relay_delay = trip_time - fault_time
pickup_start, pickup_end = 2.0, 7.0
pickup_increment, pickup_rate_limit, pickup_sample = 0.10, 0.02, 0.05
governor_rate_limit = 0.10

# Fault and time-coordinated line-clearing action on branch 11 (buses 5-8).
fault_affect = ComponentAffect([:piline₊shortcircuit]) do u, ctx
    u[:piline₊shortcircuit] = 1
    push!(events, (time_s=Float64(ctx.t), event="three_phase_fault",
                   component="branch_11", detail="fault applied"))
end
trip_affect = ComponentAffect([:piline₊active]) do u, ctx
    u[:piline₊active] = 0
    push!(events, (time_s=Float64(ctx.t), event="protection_line_trip",
                   component="branch_11", detail="100-ms fault-clearing trip"))
end
set_callback!(nw, EIndex(11), (
    PresetTimeComponentCallback(fault_time, fault_affect),
    PresetTimeComponentCallback(trip_time, trip_affect)
))

function applied_multiplier(t, scenario)
    if scenario == "hold" || t < pickup_start
        return 1.0
    elseif scenario == "step"
        return 1.0 + pickup_increment
    else
        elapsed = floor(max(0.0, t - pickup_start) / pickup_sample + 1e-9) * pickup_sample
        return 1.0 + min(pickup_increment, elapsed * pickup_rate_limit)
    end
end
function command_multiplier(t, scenario)
    (scenario == "hold" || t < pickup_start) ? 1.0 : 1.0 + pickup_increment
end

# Sampled feeder pickup actuator. The step case is an intentionally
# inadmissible diagnostic; the rate_limited case enforces the 0.02 pu/s ramp.
if scenario != "hold"
    times = scenario == "step" ? [pickup_start] : collect(pickup_start:pickup_sample:pickup_end)
    for row in eachrow(load_df)
        bus, p0, q0 = Int(row.bus), Float64(row.Pset), Float64(row.Qset)
        affect = ComponentAffect([:ZIPLoad₊Pset, :ZIPLoad₊Qset]) do u, ctx
            alpha = applied_multiplier(Float64(ctx.t), scenario)
            u[:ZIPLoad₊Pset] = p0 * alpha
            u[:ZIPLoad₊Qset] = q0 * alpha
            push!(events, (time_s=Float64(ctx.t), event="load_pickup_update",
                           component="bus_$(bus)", detail="load_multiplier=$(alpha)"))
        end
        set_callback!(nw, VIndex(bus), PresetTimeComponentCallback(times, affect))
    end
end

prob = ODEProblem(nw, NWState(nw), (0.0, 15.0))
sol = solve(prob, Rodas5P(); dtmax=0.01, save_everystep=false)
successful = SciMLBase.successful_retcode(sol)
successful || error("Dynamic simulation failed: $(sol.retcode)")

sample_times = collect(0.0:0.01:15.0)
machine_buses = Int.(machine_df.bus)
machine_H = Float64.(machine_df.H)
machine_Sn = Float64.(machine_df.Sn)
coi_weights = machine_H .* machine_Sn
gov_bus_set = Set(Int.(gov_df.bus))
omega_columns = Vector{Vector{Float64}}()
for row in eachrow(machine_df)
    bus = Int(row.bus)
    idx = VIndex(bus, bus in gov_bus_set ?
        Symbol("ctrld_gen₊machine₊ω") : Symbol("machine₊ω"))
    push!(omega_columns, vec(Float64.(sol(sample_times; idxs=idx).u)))
end
omega_matrix = hcat(omega_columns...)
frequency_matrix = 60.0 .* omega_matrix
coi_frequency = (frequency_matrix * coi_weights) ./ sum(coi_weights)
frequency_deviation = coi_frequency .- 60.0
dt = sample_times[2] - sample_times[1]
rocof = similar(coi_frequency)
rocof[1] = (coi_frequency[2] - coi_frequency[1]) / dt
rocof[end] = (coi_frequency[end] - coi_frequency[end-1]) / dt
for k in 2:(length(sample_times)-1)
    rocof[k] = (coi_frequency[k+1] - coi_frequency[k-1]) / (2dt)
end

frequency_df = DataFrame(time_s=sample_times,
    coi_frequency_hz=coi_frequency,
    coi_frequency_deviation_hz=frequency_deviation,
    coi_rocof_hz_per_s=rocof)
for (j, bus) in enumerate(machine_buses)
    frequency_df[!, Symbol("gen_bus_$(bus)_frequency_hz")] = frequency_matrix[:, j]
end
CSV.write(joinpath(outdir, "frequency_trace.csv"), frequency_df)

governor_rows = NamedTuple[]
governor_valves = Vector{Vector{Float64}}()
for row in eachrow(gov_df)
    bus = Int(row.bus)
    valve = vec(Float64.(sol(sample_times; idxs=VIndex(bus, Symbol("ctrld_gen₊gov₊xg1"))).u))
    turbine = vec(Float64.(sol(sample_times; idxs=VIndex(bus, Symbol("ctrld_gen₊gov₊xg2"))).u))
    push!(governor_valves, valve)
    for k in eachindex(sample_times)
        push!(governor_rows, (time_s=sample_times[k], bus=bus,
            valve_position_pu=valve[k], turbine_state_pu=turbine[k]))
    end
end
CSV.write(joinpath(outdir, "governor_actuator_trace.csv"), DataFrame(governor_rows))

actuator_times = collect(0.0:pickup_sample:15.0)
actuator_rows = NamedTuple[]
for k in eachindex(actuator_times)
    t = actuator_times[k]
    applied = applied_multiplier(t, scenario)
    push!(actuator_rows, (
        time_s=t,
        command_multiplier=command_multiplier(t, scenario),
        applied_multiplier=applied,
        actuator_rate_pu_per_s=k == 1 ? 0.0 :
            (applied - applied_multiplier(actuator_times[k-1], scenario)) / pickup_sample,
        actuator_rate_limit_pu_per_s=pickup_rate_limit,
        actuator_min_pu=1.0,
        actuator_max_pu=1.0 + pickup_increment))
end
actuator_df = DataFrame(actuator_rows)
CSV.write(joinpath(outdir, "feeder_pickup_actuator_trace.csv"), actuator_df)
CSV.write(joinpath(outdir, "protection_events.csv"), DataFrame(events))

valve_rate_max = maximum(maximum(abs.(diff(v))) / dt for v in governor_valves)
actuator_rate_max = maximum(abs.(actuator_df.actuator_rate_pu_per_s))
report = Dict(
    "study" => "IEEE39 full-order electromechanical transient simulation",
    "scenario" => scenario,
    "backend" => "PowerDynamics.jl; sixth-order Sauer-Pai; AVR Type-I; rate-limited TGOV1; ZIP loads; PiLine_fault",
    "power_base_mva" => 100.0,
    "frequency_base_hz" => 60.0,
    "machine_count" => length(machine_buses),
    "governor_count" => nrow(gov_df),
    "avr_count" => nrow(avr_df),
    "fault_branch_index" => 11,
    "fault_branch_buses" => [5, 8],
    "fault_start_s" => fault_time,
    "protection_trip_s" => trip_time,
    "protection_clearing_delay_s" => relay_delay,
    "protection_model_scope" => "scheduled 100-ms fault-clearing line trip; not an inverse-time overcurrent relay",
    "governor_valve_limits_pu" => [0.0, 1.0],
    "governor_valve_rate_limit_pu_per_s" => governor_rate_limit,
    "measured_max_governor_valve_rate_pu_per_s" => valve_rate_max,
    "governor_valve_amplitude_pass" => minimum(valve_all) >= -1e-5 && maximum(valve_all) <= 1.0 + 1e-5,
    "governor_valve_rate_pass" => valve_rate_max <= governor_rate_limit + 0.015,
    "feeder_pickup_command_target_pu" => 1.0 + pickup_increment,
    "feeder_pickup_rate_limit_pu_per_s" => pickup_rate_limit,
    "measured_max_feeder_pickup_rate_pu_per_s" => actuator_rate_max,
    "feeder_pickup_amplitude_range_pu" => [minimum(actuator_df.applied_multiplier), maximum(actuator_df.applied_multiplier)],
    "frequency_nadir_hz" => minimum(coi_frequency),
    "frequency_peak_hz" => maximum(coi_frequency),
    "max_abs_frequency_deviation_hz" => maximum(abs.(frequency_deviation)),
    "max_abs_rocof_hz_per_s" => maximum(abs.(rocof)),
    "max_machine_frequency_spread_hz" => maximum(maximum(frequency_matrix[k, :]) - minimum(frequency_matrix[k, :]) for k in axes(frequency_matrix, 1)),
    "solver_retcode" => string(sol.retcode),
    "solver_success" => successful,
    "sample_interval_s" => dt,
    "sample_count" => length(sample_times),
    "events" => [Dict("time_s"=>e.time_s, "event"=>e.event, "component"=>e.component, "detail"=>e.detail) for e in events],
    "interpretation_boundary" => "Synthetic IEEE39 benchmark; feeder pickup rate is an explicit aggregate actuator assumption. Not EMT switching or field-hardware validation."
)
open(joinpath(outdir, "dynamic_summary.json"), "w") do io
    JSON.print(io, report, 2)
end
println(JSON.json(report))
