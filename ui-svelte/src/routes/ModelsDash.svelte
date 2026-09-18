<script lang="ts">
  import { models } from "../stores/api";
  import ModelCard from "../lib/ModelCard.svelte";

  let visibleModels = $derived($models);
</script>

<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 p-4">
  {#each visibleModels as model (model.id)}
    <ModelCard {model} />
  {/each}
</div>
