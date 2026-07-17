<script lang="ts">
  type Job = {
    company: string; title: string; location: string; url: string;
    posted_at: string; first_seen: string; matched: number;
  };
  type Meta = {
    companies: { name: string; count: number }[];
    total: number; matched: number; last_run: string | null; alerts: string[];
  };

  let meta = $state<Meta | null>(null);
  let jobs = $state<Job[]>([]);
  let total = $state(0);
  let q = $state('');
  let company = $state('');
  let matchedOnly = $state(false);
  let loading = $state(false);

  async function load(offset = 0) {
    loading = true;
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (company) params.set('company', company);
    if (matchedOnly) params.set('matched', '1');
    params.set('offset', String(offset));
    const res: { total: number; jobs: Job[] } =
      await (await fetch(`/api/jobs?${params}`)).json();
    total = res.total;
    jobs = offset ? [...jobs, ...res.jobs] : res.jobs;
    loading = false;
  }

  let debounce: ReturnType<typeof setTimeout>;
  $effect(() => {
    // touch deps so the effect re-runs on any filter change
    void q; void company; void matchedOnly;
    clearTimeout(debounce);
    debounce = setTimeout(() => load(), 250);
  });

  fetch('/api/meta').then(r => r.json()).then(m => (meta = m));

  const ago = (iso: string) => {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d}d ago`;
  };
</script>

<header class="site">
  <div class="nav">
    <span class="brand"><span class="dot"></span>JobCrawler</span>
    {#if meta}
      <p class="stats">
        {meta.total.toLocaleString()} jobs / {meta.companies.length} co /
        {meta.matched} matched
        {#if meta.last_run}/ run {ago(meta.last_run)}{/if}
      </p>
    {/if}
  </div>
</header>

<div class="page">
  {#if meta?.alerts.length}
    <div class="alerts">
      <span class="label">Health</span>
      {#each meta.alerts as a}<p>{a}</p>{/each}
    </div>
  {/if}

  <div class="filters">
    <input type="search" placeholder="search title or location" bind:value={q} />
    <select bind:value={company}>
      <option value="">all companies</option>
      {#each meta?.companies ?? [] as c}
        <option value={c.name}>{c.name} ({c.count})</option>
      {/each}
    </select>
    <button class="toggle" class:on={matchedOnly}
      onclick={() => (matchedOnly = !matchedOnly)}>matched</button>
  </div>

  <p class="count">{total.toLocaleString()} results</p>

  <main>
    {#each jobs as j, i}
      <a class="card" class:matched={j.matched} href={j.url} target="_blank" rel="noreferrer">
        <div class="top">
          <span class="idx">{String(i + 1).padStart(3, '0')}</span>
          <span class="company">{j.company}</span>
          {#if j.matched}<span class="badge">match</span>{/if}
          <span class="when">{ago(j.first_seen)}</span>
        </div>
        <h2>{j.title}</h2>
        {#if j.location}<p class="loc">{j.location}</p>{/if}
      </a>
    {:else}
      {#if !loading}<p class="empty">no jobs found</p>{/if}
    {/each}
  </main>

  {#if jobs.length < total}
    <button class="more" onclick={() => load(jobs.length)} disabled={loading}>
      {loading ? 'loading' : 'load more'}
    </button>
  {/if}
</div>

<style>
  /* masthead: dark warm brown anchoring the page, tied in by the shared border color */
  header.site {
    position: sticky; top: 0; z-index: 50; padding: 8px 0;
    background: #2B1E19; color: #F4EBE1;
    border-bottom: 2px solid var(--color-border);
  }
  .nav {
    max-width: 44rem; margin: 0 auto; padding: 0 1rem;
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 1rem; flex-wrap: wrap;
  }
  .brand {
    display: inline-flex; align-items: center; gap: 10px;
    font-weight: 700; font-size: 20px; letter-spacing: -0.01em;
    font-style: italic;
  }
  .dot {
    width: 12px; height: 12px; border-radius: 50%;
    background: var(--color-hero); border: 2px solid #F4EBE1;
    align-self: center;
  }
  .stats {
    margin: 0; font-family: var(--mono); font-size: 0.65rem;
    text-transform: uppercase; letter-spacing: 0.12em;
    color: #C5B3A2;
  }

  .page { max-width: 44rem; margin: 0 auto; padding: 0 1rem 3rem; }

  .label {
    display: inline-block; font-size: 0.7rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.14em;
    background: var(--color-ink); color: #fff;
    padding: 0.1rem 0.5rem; border-radius: 4px; margin-bottom: 0.25rem;
  }

  .alerts {
    background: var(--color-card); border: 1.5px solid var(--color-hero);
    border-radius: var(--radius); box-shadow: var(--shadow);
    padding: 0.75rem 1rem; margin-top: 24px; font-size: 0.9rem;
  }
  .alerts p { margin: 0.25rem 0; }

  .filters {
    display: flex; flex-wrap: wrap; gap: 8px; align-items: stretch;
    margin: 24px 0 0;
  }
  input[type='search'], select, .toggle {
    border: 1.5px solid var(--color-border); border-radius: 999px;
    padding: 8px 16px; font-family: var(--display); font-size: 0.9rem;
    background: var(--color-card); color: var(--color-ink);
    transition: box-shadow var(--ease), transform var(--ease),
      border-color var(--ease), background var(--ease);
  }
  input[type='search'] { flex: 1; min-width: 12rem; }
  input[type='search']::placeholder { color: var(--color-meta); font-style: italic; }
  input[type='search']:focus, select:focus {
    outline: none; box-shadow: 0 0 0 3px rgba(244, 81, 30, 0.4);
  }
  select, .toggle { cursor: pointer; }
  select:hover { border-color: var(--color-hero); }
  .toggle:hover { border-color: var(--color-hero); }
  .toggle {
    font-weight: 600; font-size: 0.8rem;
    text-transform: uppercase; letter-spacing: 0.08em;
  }
  .toggle.on {
    /* hero-deep, not hero: white text needs the darker rust for 4.5:1 */
    background: var(--color-hero-deep); color: #fff;
    border-color: var(--color-hero-deep);
  }

  .count {
    font-family: var(--mono); color: var(--color-meta); font-size: 0.7rem;
    margin: 16px 0; text-transform: uppercase; letter-spacing: 0.12em;
  }

  main { display: grid; gap: 16px; }
  .card {
    display: block; background: var(--color-card);
    border: 1.5px solid var(--color-border);
    border-radius: var(--radius); box-shadow: var(--shadow);
    padding: 16px 20px; text-decoration: none; color: inherit;
    transition: transform var(--ease), box-shadow var(--ease),
      border-color var(--ease);
  }
  .card:hover {
    transform: translateY(-2px); box-shadow: var(--shadow-up);
    border-color: var(--color-hero);
  }
  .card:hover h2 { color: var(--color-hero-deep); }
  .card:active { transform: translateY(0); box-shadow: var(--shadow); }

  /* matched: the only place orange marks state */
  .card.matched { border-color: var(--color-hero); }
  .card.matched:hover { border-color: var(--color-hero); }

  .top {
    display: flex; gap: 12px; align-items: baseline;
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em;
  }
  .idx { font-family: var(--mono); color: var(--color-meta); }
  .company { font-weight: 600; color: var(--color-indigo); letter-spacing: 0.12em; }
  .badge {
    background: var(--color-hero-deep); color: #fff;
    border-radius: 999px; padding: 1px 10px;
    font-size: 0.62rem; font-weight: 600; letter-spacing: 0.1em;
  }
  .when { margin-left: auto; font-family: var(--mono); font-size: 0.68rem; color: var(--color-meta); }
  h2 {
    font-weight: 600; font-size: 1.15rem; line-height: 1.3;
    margin: 4px 0 2px; color: var(--color-ink); transition: color var(--ease);
  }
  .loc { margin: 0; font-size: 0.85rem; font-style: italic; color: var(--color-meta); }
  .empty {
    text-align: center; color: var(--color-meta); padding: 32px;
    font-style: italic; font-size: 1rem;
  }

  .more {
    display: block; margin: 24px auto 0;
    border: 1.5px solid var(--color-indigo); border-radius: 999px;
    background: var(--color-indigo); color: #fff; box-shadow: var(--shadow);
    padding: 10px 28px; font-family: var(--display); font-weight: 600;
    font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.1em;
    cursor: pointer; transition: transform var(--ease), box-shadow var(--ease),
      background var(--ease), border-color var(--ease);
  }
  .more:hover {
    transform: translateY(-2px); box-shadow: var(--shadow-up);
    background: var(--color-hero-deep); border-color: var(--color-hero-deep);
  }
  .more:active { transform: translateY(0); box-shadow: var(--shadow); }
  .more:disabled { opacity: 0.6; cursor: default; }
</style>
