import {useEffect, useState} from 'react';
import {
  Badge, Banner, Button, Checkbox, EmptyState, ProgressBar,
  Select, TextField, Toast,
} from '@shopify/polaris';
import {Link, NavLink, Route, Routes, useNavigate, useParams} from 'react-router-dom';
import {api} from './api';
import {demoJobs, demoProducts, generatedImages, promptIdeas} from './demo';

const navigation = [
  ['/', 'Overview', '◈'],
  ['/products', 'Products', '▦'],
  ['/generate', 'Create', '✦'],
  ['/history', 'History', '↺'],
  ['/billing', 'Plan & credits', '◇'],
];

function shopifySearch() {
  const current = new URLSearchParams(location.search);
  const preserved = new URLSearchParams();
  ['shop', 'host', 'embedded'].forEach(key => {
    const value = current.get(key);
    if (value) preserved.set(key, value);
  });
  const query = preserved.toString();
  return query ? `?${query}` : '';
}

function shopifyTo(path) {
  return `${path}${shopifySearch()}`;
}

function App() {
  const [products, setProducts] = useState(demoProducts);
  const [jobs, setJobs] = useState(demoJobs);
  const [account, setAccount] = useState({plan: 'Pro', credits_balance: 86, images_this_month: 42});
  const [demo, setDemo] = useState(false);
  const [apiError, setApiError] = useState('');

  useEffect(() => {
    Promise.all([api.me(), api.products(), api.jobs()])
      .then(([me, productData, jobData]) => {
        setAccount(me);
        if (productData.length) setProducts(productData);
        if (jobData.length) setJobs(jobData);
      })
      .catch(error => {
        setApiError(error.message);
        setDemo(true);
      });
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to={shopifyTo('/')}>
          <span className="brand-mark">P</span>
          <span>PixelMint <b>AI</b></span>
        </Link>
        <nav>
          {navigation.map(([to, label, icon]) => (
            <NavLink key={to} to={shopifyTo(to)} end={to === '/'} className={({isActive}) => isActive ? 'nav-link active' : 'nav-link'}>
              <span>{icon}</span>{label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="credit-mini">
          <div className="credit-row"><span>Monthly credits</span><strong>{account.credits_balance}</strong></div>
          <ProgressBar progress={Math.min(100, account.credits_balance)} size="small" tone="success" />
          <span className="muted">Resets in 12 days</span>
        </div>
        <div className="store-chip"><span className="store-avatar">A</span><span><strong>Aurelia Goods</strong><small>demo-store.myshopify.com</small></span><span>•••</span></div>
      </aside>
      <main className="main">
        {demo && <div className="demo-bar">API fallback mode · {apiError || 'connect the Django API to use your store data'}</div>}
        <Routes>
          <Route path="/" element={<Dashboard account={account} jobs={jobs} />} />
          <Route path="/products" element={<Products products={products} />} />
          <Route path="/generate" element={<Generate products={products} setJobs={setJobs} account={account} setAccount={setAccount} demo={demo} />} />
          <Route path="/generate/:productId" element={<Generate products={products} setJobs={setJobs} account={account} setAccount={setAccount} demo={demo} />} />
          <Route path="/history" element={<History jobs={jobs} />} />
          <Route path="/billing" element={<Billing account={account} />} />
        </Routes>
      </main>
    </div>
  );
}

function PageHeader({eyebrow, title, description, action}) {
  return <header className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</header>;
}

function Dashboard({account, jobs}) {
  return <div className="page">
    <PageHeader eyebrow="THURSDAY, JUNE 25" title="Good morning, Aurelia." description="Your catalog has a few fresh opportunities waiting." action={<Button variant="primary" url={shopifyTo('/generate')}>✦ Create product images</Button>} />
    <section className="metrics">
      <div className="metric accent"><span className="metric-icon">✦</span><span>Credits available</span><strong>{account.credits_balance}</strong><small>of 400 this month</small></div>
      <div className="metric"><span className="metric-icon mint">↗</span><span>Images this month</span><strong>{account.images_this_month || 42}</strong><small className="positive">+18% from last month</small></div>
      <div className="metric"><span className="metric-icon sand">▦</span><span>Products enhanced</span><strong>12</strong><small>across 8 collections</small></div>
    </section>
    <section className="split">
      <div className="panel">
        <div className="panel-title"><div><span className="eyebrow">QUICK START</span><h2>Make something beautiful</h2></div><span className="spark">✦</span></div>
        <div className="idea-grid">
          {[['Studio refresh', 'Clean, conversion-ready product shots', '01'], ['In the wild', 'Lifestyle scenes with real atmosphere', '02'], ['Campaign mode', 'Bold creative for your next launch', '03']].map(([title, copy, number]) =>
            <Link to={shopifyTo('/generate')} className="idea" key={title}><span>{number}</span><div><strong>{title}</strong><small>{copy}</small></div><b>→</b></Link>)}
        </div>
      </div>
      <div className="panel tip-card"><span className="eyebrow">CREATIVE NOTE</span><blockquote>“Keep the product true. Change the world around it.”</blockquote><p>Reference images help PixelMint preserve the details your customers care about.</p><Link to={shopifyTo('/generate')}>Start with a reference →</Link></div>
    </section>
    <section className="panel recent">
      <div className="panel-title"><div><span className="eyebrow">RECENT WORK</span><h2>Latest generations</h2></div><Button variant="plain" url={shopifyTo('/history')}>View all</Button></div>
      <div className="job-list">{jobs.slice(0, 3).map(job => <JobRow job={job} key={job.id} />)}</div>
    </section>
  </div>;
}

function JobRow({job}) {
  const image = job.images?.[0]?.url || job.product.images?.[0]?.url;
  return <div className="job-row"><img src={image} /><div><strong>{job.product.title}</strong><small>{new Date(job.created_at).toLocaleDateString()} · {job.images?.length || 0} images</small></div><Badge tone={job.status === 'completed' ? 'success' : 'attention'}>{job.status}</Badge><span className="muted">{job.credits_used} credits</span><button className="round-button">→</button></div>;
}

function Products({products}) {
  const [query, setQuery] = useState('');
  const filtered = products.filter(p => p.title.toLowerCase().includes(query.toLowerCase()));
  return <div className="page">
    <PageHeader eyebrow="YOUR CATALOG" title="Choose a product" description="Pick a product and we’ll build the creative direction together." />
    <div className="toolbar"><div className="search"><TextField label="Search products" labelHidden value={query} onChange={setQuery} placeholder="Search products…" autoComplete="off" /></div><Select label="Status" labelHidden options={['All products', 'Active', 'Draft']} /><Button>Sync Shopify</Button></div>
    <div className="product-grid">{filtered.map(product => <ProductCard product={product} key={product.id} />)}</div>
  </div>;
}

function ProductCard({product}) {
  return <article className="product-card">
    <div className="product-image"><img src={product.images?.[0]?.url} /><Badge tone={product.status === 'ACTIVE' ? 'success' : 'attention'}>{product.status}</Badge></div>
    <div className="product-copy"><span>{product.vendor}</span><h3>{product.title}</h3><small>{product.product_type}</small><Button variant="primary" url={shopifyTo(`/generate/${product.id}`)}>Create images</Button></div>
  </article>;
}

function Generate({products, setJobs, account, setAccount, demo}) {
  const {productId} = useParams();
  const navigate = useNavigate();
  const initial = products.find(p => String(p.id) === productId) || products[0];
  const [step, setStep] = useState(1);
  const [product, setProduct] = useState(initial);
  const [references, setReferences] = useState([0]);
  const [prompts, setPrompts] = useState(promptIdeas.map((prompt, id) => ({id, prompt, is_selected: id < 4})));
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [jobId, setJobId] = useState(null);

  const selectedPromptCount = prompts.filter(p => p.is_selected).length;

  async function createPrompts() {
    setBusy(true);
    try {
      if (!demo) {
        const job = await api.createJob(product.id, references.map(i => product.images[i]?.url).filter(Boolean));
        const ready = await api.generatePrompts(job.id);
        setJobId(job.id);
        setPrompts(ready.prompts);
      }
      setStep(3);
    } catch (error) { setToast(error.message); }
    finally { setBusy(false); }
  }

  async function createImages() {
    if (selectedPromptCount > account.credits_balance) return setToast('Not enough credits for this generation.');
    setBusy(true); setStep(4);
    try {
      if (!demo && jobId) {
        await api.generateImages(jobId, prompts);
        await new Promise(resolve => setTimeout(resolve, 2500));
      }
      await new Promise(resolve => setTimeout(resolve, 1500));
      const made = generatedImages.slice(0, selectedPromptCount).map((url, index) => ({id: index + 1, url, status: 'completed'}));
      setResults(made); setSelected(made.map(image => image.id));
      setAccount(value => ({...value, credits_balance: value.credits_balance - selectedPromptCount}));
      setStep(5);
    } catch (error) { setToast(error.message); setStep(3); }
    finally { setBusy(false); }
  }

  function finish() {
    const job = {id: Date.now(), product, status: 'completed', created_at: new Date().toISOString(), credits_used: selectedPromptCount, images: results.filter(i => selected.includes(i.id))};
    setJobs(current => [job, ...current]);
    setToast(demo ? 'Demo complete — connect Shopify to publish these images.' : 'Images added to your product.');
    setTimeout(() => navigate(shopifyTo('/history')), 1200);
  }

  return <div className="page wizard-page">
    <PageHeader eyebrow="AI IMAGE STUDIO" title={step === 1 ? 'Start with a product' : product.title} description="Build a cohesive set of product images in a few focused steps." />
    <div className="stepper">{['Product', 'References', 'Directions', 'Generating', 'Review'].map((label, i) => <div className={step >= i + 1 ? 'step active' : 'step'} key={label}><span>{step > i + 1 ? '✓' : i + 1}</span><small>{label}</small></div>)}</div>
    {step === 1 && <section className="wizard-card">
      <span className="eyebrow">STEP 1 OF 5</span><h2>What are we photographing?</h2>
      <div className="compact-products">{products.map(item => <button className={product.id === item.id ? 'compact-product selected' : 'compact-product'} onClick={() => setProduct(item)} key={item.id}><img src={item.images?.[0]?.url} /><span><strong>{item.title}</strong><small>{item.vendor} · {item.product_type}</small></span><b>{product.id === item.id ? '✓' : ''}</b></button>)}</div>
      <div className="wizard-actions"><span /><Button variant="primary" onClick={() => setStep(2)}>Continue →</Button></div>
    </section>}
    {step === 2 && <section className="wizard-card">
      <span className="eyebrow">STEP 2 OF 5</span><h2>Choose your references</h2><p className="lead">We’ll use these to keep shape, color, materials and branding faithful.</p>
      <div className="reference-grid">{product.images.map((image, i) => <button onClick={() => setReferences(current => current.includes(i) ? current.filter(x => x !== i) : [...current, i])} className={references.includes(i) ? 'reference selected' : 'reference'} key={image.url}><img src={image.url} /><span>{references.includes(i) ? '✓ Selected' : 'Select'}</span></button>)}<button className="reference upload"><b>＋</b><span>Upload a reference</span></button></div>
      <div className="wizard-actions"><Button onClick={() => setStep(1)}>Back</Button><Button variant="primary" loading={busy} onClick={createPrompts}>Build creative directions ✦</Button></div>
    </section>}
    {step === 3 && <section className="wizard-card wide">
      <div className="panel-title"><div><span className="eyebrow">STEP 3 OF 5</span><h2>Choose creative directions</h2><p className="lead">Edit the language until it feels like your brand.</p></div><div className="credit-cost">{selectedPromptCount} images · {selectedPromptCount} credits</div></div>
      <div className="prompt-list">{prompts.map((item, index) => <div className={item.is_selected ? 'prompt selected' : 'prompt'} key={item.id ?? index}><Checkbox label="" checked={item.is_selected} onChange={value => setPrompts(current => current.map((p, i) => i === index ? {...p, is_selected: value} : p))} /><span className="prompt-number">{String(index + 1).padStart(2, '0')}</span><TextField label={`Prompt ${index + 1}`} labelHidden multiline={2} value={item.prompt} onChange={value => setPrompts(current => current.map((p, i) => i === index ? {...p, prompt: value} : p))} autoComplete="off" /></div>)}</div>
      <button className="add-prompt" onClick={() => setPrompts(current => [...current, {prompt: '', is_selected: true}])}>＋ Add your own direction</button>
      <div className="wizard-actions"><Button onClick={() => setStep(2)}>Back</Button><Button variant="primary" disabled={!selectedPromptCount} onClick={createImages}>Generate {selectedPromptCount} images ✦</Button></div>
    </section>}
    {step === 4 && <section className="generating">
      <div className="orb"><span>✦</span></div><span className="eyebrow">CREATING YOUR SET</span><h2>Setting the scene…</h2><p>PixelMint is preserving the product while crafting each world around it.</p><div className="generation-progress"><ProgressBar progress={70} tone="success" /><small>{selectedPromptCount} compositions in progress</small></div>
    </section>}
    {step === 5 && <section className="wizard-card wide">
      <div className="panel-title"><div><span className="eyebrow">STEP 5 OF 5</span><h2>Your new image set</h2><p className="lead">Select the strongest images to add to Shopify.</p></div><Badge tone="success">{selected.length} selected</Badge></div>
      <div className="result-grid">{results.map(image => <button onClick={() => setSelected(current => current.includes(image.id) ? current.filter(x => x !== image.id) : [...current, image.id])} className={selected.includes(image.id) ? 'result selected' : 'result'} key={image.id}><img src={image.url} /><span>{selected.includes(image.id) ? '✓' : ''}</span><div><b>Download</b><b>↻</b></div></button>)}</div>
      <div className="wizard-actions"><Button onClick={() => setStep(3)}>Refine directions</Button><Button variant="primary" disabled={!selected.length} onClick={finish}>Add {selected.length} to product →</Button></div>
    </section>}
    {toast && <Toast content={toast} onDismiss={() => setToast('')} />}
  </div>;
}

function History({jobs}) {
  return <div className="page"><PageHeader eyebrow="YOUR ARCHIVE" title="Generation history" description="Every creative set, ready to revisit." action={<Button variant="primary" url={shopifyTo('/generate')}>New generation</Button>} />
    {jobs.length ? <div className="history-grid">{jobs.map(job => <article className="history-card" key={job.id}><div className="history-images">{job.images?.slice(0, 3).map(image => <img src={image.url} key={image.id} />)}</div><div className="history-copy"><div><span className="eyebrow">{new Date(job.created_at).toLocaleDateString()}</span><h3>{job.product.title}</h3><small>{job.images?.length} images · {job.credits_used} credits</small></div><Button>Open set</Button></div></article>)}</div> : <EmptyState heading="No generations yet" action={{content: 'Create images', url: '/generate'}} />}
  </div>;
}

function Billing({account}) {
  const plans = [
    {name: 'Free', price: 0, credits: 10}, {name: 'Starter', price: 9, credits: 100},
    {name: 'Pro', price: 29, credits: 400, featured: true}, {name: 'Growth', price: 79, credits: '1,500'},
  ];
  return <div className="page"><PageHeader eyebrow="PLAN & CREDITS" title="Room to keep creating" description={`You have ${account.credits_balance} credits left in this billing cycle.`} />
    <Banner title="Credits are only used for completed images" tone="info">Failed generations are automatically refunded to your balance.</Banner>
    <div className="plan-grid">{plans.map(plan => <article className={plan.featured ? 'plan featured' : 'plan'} key={plan.name}>{plan.featured && <span className="popular">CURRENT PLAN</span>}<span className="eyebrow">{plan.name}</span><div className="price"><strong>${plan.price}</strong><small>/ month</small></div><p><b>{plan.credits}</b> image credits each month</p><ul><li>All creative directions</li><li>High-resolution exports</li><li>Shopify product publishing</li></ul><Button variant={plan.featured ? 'primary' : 'secondary'} fullWidth disabled={plan.featured}>{plan.featured ? 'Your current plan' : 'Choose plan'}</Button></article>)}</div>
  </div>;
}

export default App;
