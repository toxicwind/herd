<script>
  export let model;
</script>

<div class="card">
  <h3>{model.name}</h3>
  <p>{model.description || 'No description available.'}</p>
  <div class="tags">
    {#each (model.tags || []) as tag}
      <span class="tag">{tag}</span>
    {/each}
  </div>
</div>

<style>
  .card {
    border: 1px solid #ccc;
    padding: 1rem;
    border-radius: 8px;
    background: #fff;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  }
  .tag {
    background: #eee;
    padding: 2px 6px;
    border-radius: 4px;
    margin-right: 4px;
    font-size: 0.8rem;
  }
</style>
