# IoT-J R1: Controlled actor-versus-critic shared-object intervention

## Scientific scope

This experiment tests the effect of *which parameter block is federated* on IEEE39 AC restoration with the same local PER-DDPG learner. It does NOT reproduce or rank the published A2FC algorithm.

The actor arm shares actor.backbone; local actor encoder, head and the entire critic remain personalized. The critic arm shares only critic layers 2–4 (common hidden/output block); the observation-dependent critic input layer and all actor modules remain personalized. This permits heterogeneous observation dimensions in hetero=dim without padding or replacing the learner.

Both arms execute identical local_fit and the same advantage-conditioned local actor update via Agent.share each round. In the actor arm its update is federated; in the critic arm its update is retained locally and a compatible critic-subblock Top-k update is federated instead. The same Server.step function implements clipping, prototype metadata, credibility scoring, Byzantine message modification and aggregation in both arms. Actor and critic gradients remain different objectives: this is a shared-block architectural intervention, not a claim that their optimization is mathematically identical.

## Matched communication budget

Transmit the SAME ABSOLUTE number of Top-k index/value pairs in both arms: ceil(0.2 * actor_backbone_parameter_count). The critic compatible block is smaller, so its sparse proportion differs. Utility and three prototype category fields use identical serialized fixed padding. Audit real application message lengths via strict_agent.serialized_size and compare every round for paired arms. This measures constructed serialized APPLICATION-LAYER uplink bytes (not network wire bytes or downstream traffic), and must be distinguished from analytical estimates.

## Design and interpretation

Primary: actor/full versus critic/full, 10 matched seeds 80–89, clean and joint attacks.

Secondary under joint only: apply one ablation in both shared-object arms. no_adv replaces advantage-weighted sample selection with ordinary matched-count selection; no_proto disables only local prototype-alignment loss while retaining server prototypes; no_cred sets equal aggregation weights while preserving clipping and message schema.

Full budget: 1000 training episodes, 200 federation rounds, five clients, hetero=dim, batch 256, hidden 128, latent 32, local_fit 5 updates and Agent.share 2 steps each round, fixed serialized uplink, 10 frozen held-out AC tests per seed. Total 100 full-budget runs (10 seeds x 2 architectures x [clean/full + four joint conditions]).

Outcome: independent-test final restored load, mean trajectory load, number of tests with load >=90% plus 5-step continuous AC safety, unsafe AC tests, malicious aggregation weights, and actual cumulative application uplink bytes. Independent unit = training seed. Audit raw traces and count all missed/unsafe trajectories; use paired contrasts and exploratory paired bootstrap confidence intervals. Do not promote smoke results to paper evidence, claim statistical significance without adequate support, or claim frequency/relay verification from quasi-static AC.

Files: shared_object_ablation.py, audit_shared_object.py, aggregate_shared_object.py, .github/workflows/iotj-76369-shared-object.yml.
