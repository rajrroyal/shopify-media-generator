import {useEffect, useState} from 'react';
import {
  Badge, Banner, Button, Checkbox, EmptyState, Frame, ProgressBar,
  Select, TextField, Toast,
} from '@shopify/polaris';
import logo from './assets/pixelmint.jpg';
import {Link, NavLink, Route, Routes, useNavigate, useParams} from 'react-router-dom';
import {api} from './api';
import {demoJobs, demoProducts, generatedImages, promptIdeas} from './demo';

const demoMode = import.meta.env.VITE_DEMO_MODE === 'true';

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

function actionProductId() {
  const resourceId = new URLSearchParams(location.search).get('id');
  if (!resourceId) return undefined;
  const productId = resourceId.replace(/\/+$/, '').split('/').pop();
  return /^\d+$/.test(productId) ? productId : undefined;
}

function promptText(value = '') {
  return value
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/\s+/g, ' ')
    .trim();
}

function promptTitle(value, index) {
  const text = promptText(value);
  const scene = text.match(/^(.{3,55}?)(?:\s+photograph|\s+photo|\s+image|\s+of\b)/i)?.[1];
  const title = scene || text.split(' ').slice(0, 5).join(' ');
  return title || `Custom idea ${index + 1}`;
}

function PromptEditor({editor, onChange, onSave, onClose}) {
  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const editing = editor.index !== null;
  return <div className="prompt-modal-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="prompt-modal" role="dialog" aria-modal="true" aria-labelledby="prompt-editor-title">
      <header>
        <div>
          <span className="eyebrow">{editing ? 'EDIT IDEA' : 'NEW IDEA'}</span>
          <h2 id="prompt-editor-title">{editing ? 'Refine this direction' : 'Add a custom direction'}</h2>
        </div>
        <button className="prompt-modal-close" onClick={onClose} aria-label="Close prompt editor">×</button>
      </header>
      <p>Describe the scene, composition, lighting and details you want PixelMint to preserve.</p>
      <label className="prompt-editor-field">
        <span>Image prompt</span>
        <textarea
          autoFocus
          maxLength={4000}
          rows={10}
          value={editor.value}
          onChange={event => onChange(event.target.value)}
          placeholder="Example: Clean studio photograph on a warm neutral backdrop with soft directional light…"
        />
      </label>
      <div className="prompt-editor-meta">
        <span className={editor.error ? 'prompt-editor-error' : ''}>{editor.error || 'Be specific, but keep the product true to its original appearance.'}</span>
        <span>{editor.value.length.toLocaleString()} / 4,000</span>
      </div>
      <footer>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={onSave}>{editing ? 'Save changes' : 'Add direction'}</Button>
      </footer>
    </section>
  </div>;
}

function ImageLightbox({images, initialIndex, onClose}) {
  const [activeIndex, setActiveIndex] = useState(initialIndex ?? 0);

  useEffect(() => {
    setActiveIndex(initialIndex ?? 0);
  }, [initialIndex]);

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  if (!images?.length || initialIndex === null || initialIndex === undefined) return null;
  const activeImage = images[activeIndex] || images[0];
  if (!activeImage?.url) return null;

  return <div className="prompt-modal-backdrop image-lightbox-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="image-lightbox" role="dialog" aria-modal="true" aria-label="Image preview">
      <button className="prompt-modal-close image-lightbox-close" onClick={onClose} aria-label="Close image preview">×</button>
      <img src={activeImage.url} alt="Preview" />
      {images.length > 1 && <div className="image-lightbox-controls">
        <button type="button" onClick={() => setActiveIndex(current => (current - 1 + images.length) % images.length)} aria-label="Previous image">←</button>
        <span>{activeIndex + 1} / {images.length}</span>
        <button type="button" onClick={() => setActiveIndex(current => (current + 1) % images.length)} aria-label="Next image">→</button>
      </div>}
    </section>
  </div>;
}

function App() {
  const [products, setProducts] = useState(demoMode ? demoProducts : []);
  const [jobs, setJobs] = useState(demoMode ? demoJobs : []);
  const [account, setAccount] = useState(demoMode
    ? {shop_name: 'Aurelia Goods', shop_domain: 'demo-store.myshopify.com', plan: 'pro', credits_balance: 86, credit_limit: 400, images_this_month: 42}
    : {shop_name: '', shop_domain: '', plan: 'free', credits_balance: 0, credit_limit: 10, images_this_month: 0, products_enhanced: 0});
  const [loading, setLoading] = useState(!demoMode);
  const [apiError, setApiError] = useState('');

  useEffect(() => {
    if (demoMode) return;
    async function loadHistory() {
      try {
        setJobs(await api.jobs());
      } catch (error) {
        setApiError(error.message);
      } finally {
        setLoading(false);
      }
    }
    async function loadAccount() {
      try {
        setAccount(await api.me());
      } catch (error) {
        setApiError(error.message);
      }
    }
    loadHistory();
    loadAccount();
  }, []);

  const storeName = account.shop_name || account.shop_domain || 'Your store';
  const initial = storeName.charAt(0).toUpperCase();

  return (
    <Frame>
      <div className="app-shell">
        <header className="topbar">
          <Link className="brand" to={shopifyTo('/')}>
            <img className="brand-logo" src={logo} alt="PixelMint logo" />
            <span>PixelMint <sup className="brand-sup">AI</sup></span>
          </Link>
          <nav className="top-nav" aria-label="Primary navigation">
            {navigation.map(([to, label, icon]) => (
              <NavLink key={to} to={shopifyTo(to)} end={to === '/'} className={({isActive}) => isActive ? 'nav-link active' : 'nav-link'}>
                <span>{icon}</span>{label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-account">
            <Link className="credit-pill" to={shopifyTo('/billing')}>
              <span>✦</span><strong>{account.credits_balance}</strong><small>credits</small>
            </Link>
          </div>
        </header>
        <main className="main">
          {loading && <AppMessage tone="info" title="Preparing your workspace" message="Loading your store details and recent generations…" />}
          {demoMode && <AppMessage tone="info" title="Demo mode" message="Shopify publishing is paused while demo mode is active." />}
          {apiError && <AppMessage tone="critical" title="We couldn’t access your store" message={apiError} onDismiss={() => setApiError('')} />}
          <Routes>
            <Route path="/" element={<Dashboard account={account} jobs={jobs} loading={loading} />} />
            <Route path="/products" element={<Products products={products} setProducts={setProducts} />} />
            <Route path="/generate" element={<Generate products={products} setProducts={setProducts} setJobs={setJobs} account={account} setAccount={setAccount} demo={demoMode} />} />
            <Route path="/generate/:productId" element={<Generate products={products} setProducts={setProducts} setJobs={setJobs} account={account} setAccount={setAccount} demo={demoMode} />} />
            <Route path="/history" element={<History jobs={jobs} />} />
            <Route path="/billing" element={<Billing account={account} setAccount={setAccount} />} />
          </Routes>
        </main>
      </div>
    </Frame>
  );
}

function AppMessage({tone, title, message, onDismiss}) {
  return <div className={`app-message ${tone}`}>
    <span className="message-icon">{tone === 'critical' ? '!' : 'i'}</span>
    <div><strong>{title}</strong><small>{message}</small></div>
    {onDismiss && <button onClick={onDismiss} aria-label="Dismiss message">×</button>}
  </div>;
}

function PageHeader({eyebrow, title, description, action}) {
  return <header className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</header>;
}

function Dashboard({account, jobs, loading}) {
  const today = new Intl.DateTimeFormat(undefined, {weekday: 'long', month: 'long', day: 'numeric'}).format(new Date()).toUpperCase();
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const merchant = account.shop_name || account.shop_domain?.split('.')[0] || 'there';
  return <div className="page">
    <PageHeader eyebrow={today} title={`${greeting}, ${merchant}.`} description={loading ? 'Loading your current store…' : 'Your catalog is ready for something fresh.'} action={<Button variant="primary" url={shopifyTo('/generate')}>✦ Create product images</Button>} />
    <section className="metrics">
      <div className="metric accent"><span className="metric-icon">✦</span><span>Credits available</span><strong>{account.credits_balance}</strong><small>of {account.credit_limit || 10} this month</small></div>
      <div className="metric"><span className="metric-icon mint">↗</span><span>Images this month</span><strong>{account.images_this_month || 0}</strong><small>completed generations</small></div>
      <div className="metric"><span className="metric-icon sand">▦</span><span>Products enhanced</span><strong>{account.products_enhanced || 0}</strong><small>published to Shopify</small></div>
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
      {jobs.length
        ? <div className="job-list">{jobs.slice(0, 3).map(job => <JobRow job={job} key={job.id} />)}</div>
        : <div className="inline-empty"><span>✦</span><div><strong>Your first image set starts here</strong><small>Choose a Shopify product and create a polished campaign in minutes.</small></div><Button url={shopifyTo('/products')}>Browse products</Button></div>}
    </section>
  </div>;
}

function JobRow({job}) {
  const image = job.images?.[0]?.url || job.product.images?.[0]?.url;
  return <div className="job-row">{image ? <img src={image} alt="" /> : <span className="job-placeholder">✦</span>}<div><strong>{job.product.title}</strong><small>{new Date(job.created_at).toLocaleDateString()} · {job.images?.length || 0} images</small></div><Badge tone={job.status === 'completed' ? 'success' : 'attention'}>{job.status}</Badge><span className="muted">{job.credits_used} credits</span></div>;
}

function Products({products, setProducts}) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('ALL');
  const [syncing, setSyncing] = useState(false);
  const [loading, setLoading] = useState(!products.length);
  const [toast, setToast] = useState('');
  const filtered = products.filter(p =>
    p.title.toLowerCase().includes(query.toLowerCase()) && (status === 'ALL' || p.status === status)
  );
  async function sync() {
    setSyncing(true);
    try {
      setProducts(await api.products());
      setToast('Products refreshed from Shopify.');
    } catch (error) { setToast(error.message); }
    finally { setSyncing(false); }
  }
  useEffect(() => {
    let active = true;
    if (products.length) {
      setLoading(false);
      return () => { active = false; };
    }
    api.products()
      .then(data => {
        if (active) setProducts(data);
      })
      .catch(error => {
        if (active) setToast(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [products.length, setProducts]);
  return <div className="page">
    <PageHeader eyebrow="LIVE SHOPIFY CATALOG" title="Choose a product" description="Products are loaded directly from Shopify and are never copied into PixelMint." />
    <div className="catalog-note"><span>✓</span><div><strong>Always current</strong><small>Changes made in Shopify appear here when you refresh.</small></div></div>
    <div className="toolbar"><div className="search"><TextField label="Search products" labelHidden value={query} onChange={setQuery} placeholder="Search products…" autoComplete="off" /></div><Select label="Status" labelHidden value={status} onChange={setStatus} options={[{label: 'All products', value: 'ALL'}, {label: 'Active', value: 'ACTIVE'}, {label: 'Draft', value: 'DRAFT'}]} /><Button loading={syncing} onClick={sync}>Refresh products</Button></div>
    {loading
      ? <div className="catalog-loading"><span className="loading-orb">✦</span><div><strong>Fetching your current Shopify catalog</strong><small>This is a direct API request—no local product cache or WebSocket.</small></div></div>
      : filtered.length
        ? <div className="product-grid">{filtered.map(product => <ProductCard product={product} key={product.id} />)}</div>
        : <EmptyState heading={products.length ? 'No products match these filters' : 'No Shopify products found'} action={{content: 'Refresh products', onAction: sync}} />}
    {toast && <Toast content={toast} onDismiss={() => setToast('')} />}
  </div>;
}

function ProductCard({product}) {
  const navigate = useNavigate();
  return <article className="product-card">
    <div className="product-image">{product.images?.[0]?.url ? <img src={product.images[0].url} alt="" /> : <span className="image-placeholder">No product image</span>}<Badge tone={product.status === 'ACTIVE' ? 'success' : 'attention'}>{product.status}</Badge></div>
    <div className="product-copy"><span>{product.vendor}</span><h3>{product.title}</h3><small>{product.product_type}</small><Button variant="primary" onClick={() => navigate(shopifyTo(`/generate/${product.id}`))}>Create images</Button></div>
  </article>;
}

function Generate({products, setProducts, setJobs, account, setAccount, demo}) {
  const {productId: routeProductId} = useParams();
  const productId = routeProductId || actionProductId();
  const navigate = useNavigate();
  const initial = products.find(p => String(p.id) === productId)
    || (!productId ? products[0] : undefined);
  const [step, setStep] = useState(productId ? 2 : 1);
  const [product, setProduct] = useState(initial);
  const [productLoading, setProductLoading] = useState(!initial);
  const [productError, setProductError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [references, setReferences] = useState([0]);
  const [prompts, setPrompts] = useState(promptIdeas.map((prompt, id) => ({id, prompt, is_selected: id < 4})));
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [jobId, setJobId] = useState(null);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generationMessage, setGenerationMessage] = useState('Preparing your product references…');
  const [generationSlots, setGenerationSlots] = useState([]);
  const [promptEditor, setPromptEditor] = useState(null);
  const [lightboxImages, setLightboxImages] = useState([]);
  const [lightboxIndex, setLightboxIndex] = useState(null);

  const selectedPromptCount = prompts.filter(p => p.is_selected).length;
  const allPromptsSelected = prompts.length > 0 && selectedPromptCount === prompts.length;

  useEffect(() => {
    let active = true;
    async function loadProductSelection() {
      const existing = products.find(item => String(item.id) === productId)
        || (!productId ? products[0] : null);
      if (existing) {
        if (!active) return;
        setProduct(existing);
        setReferences(existing.images?.length ? [0] : []);
        setProductLoading(false);
        setProductError('');
        return;
      }

      setProductLoading(true);
      setProductError('');
      try {
        if (demo) throw new Error('No demo products are available.');
        if (productId) {
          const selectedProduct = await api.product(productId);
          if (!active) return;
          setProduct(selectedProduct);
          setReferences(selectedProduct.images?.length ? [0] : []);
          setProducts(current => current.some(item => item.id === selectedProduct.id)
            ? current
            : [selectedProduct, ...current]);
        } else {
          const liveProducts = await api.products();
          if (!active) return;
          setProducts(liveProducts);
          setProduct(liveProducts[0] || null);
          setReferences(liveProducts[0]?.images?.length ? [0] : []);
        }
      } catch (error) {
        if (active) setProductError(error.message);
      } finally {
        if (active) setProductLoading(false);
      }
    }
    loadProductSelection();
    return () => { active = false; };
  }, [demo, loadAttempt, productId, products, setProducts]);

  function chooseProduct(item) {
    setProduct(item);
    setReferences(item.images?.length ? [0] : []);
    setJobId(null);
  }

  function togglePrompt(index) {
    setPrompts(current => current.map((prompt, promptIndex) =>
      promptIndex === index ? {...prompt, is_selected: !prompt.is_selected} : prompt
    ));
  }

  function toggleAllPrompts() {
    const nextValue = !allPromptsSelected;
    setPrompts(current => current.map(prompt => ({...prompt, is_selected: nextValue})));
  }

  function openPromptEditor(index = null) {
    setPromptEditor({
      index,
      value: index === null ? '' : prompts[index].prompt,
      error: '',
    });
  }

  function savePrompt() {
    const value = promptEditor.value.trim();
    if (!value) {
      setPromptEditor(current => ({...current, error: 'Enter a prompt before saving.'}));
      return;
    }
    setPrompts(current => promptEditor.index === null
      ? [...current, {prompt: value, is_selected: true}]
      : current.map((prompt, index) =>
          index === promptEditor.index ? {...prompt, prompt: value} : prompt
        ));
    setPromptEditor(null);
  }

  async function createPrompts() {
    if (!product) return setToast('Choose a product first.');
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
    if (!demo && !jobId) return setToast('Build creative directions before generating images.');
    setBusy(true); setStep(4); setGenerationProgress(8);
    setGenerationMessage('Preparing your product references…');
    const selectedPrompts = prompts.filter(prompt => prompt.is_selected);
    setGenerationSlots(selectedPrompts.map((prompt, index) => ({
      key: prompt.id ?? `custom-${index}`,
      status: 'waiting',
      url: '',
    })));
    setResults([]);
    setSelected([]);
    try {
      if (!demo && jobId) {
        const made = [];
        const knownImageIds = new Set();
        const existingJob = await api.job(jobId);
        existingJob.images.forEach(image => knownImageIds.add(image.id));
        let job;
        for (let index = 0; index < selectedPrompts.length; index += 1) {
          setGenerationSlots(slots => slots.map((slot, slotIndex) =>
            slotIndex === index ? {...slot, status: 'processing'} : slot
          ));
          setGenerationMessage(`Creating image ${index + 1} of ${selectedPrompts.length}…`);
          job = await api.generateImages(jobId, [selectedPrompts[index]]);
          const generated = job.images.find(image => !knownImageIds.has(image.id));
          job.images.forEach(image => knownImageIds.add(image.id));
          if (!generated || generated.status !== 'completed' || !generated.url) {
            const message = generated?.error_message || 'Image generation failed.';
            setGenerationSlots(slots => slots.map((slot, slotIndex) =>
              slotIndex === index ? {...slot, status: 'failed', error: message} : slot
            ));
            setGenerationProgress(Math.round(((index + 1) / selectedPrompts.length) * 100));
            continue;
          }
          made.push(generated);
          setResults([...made]);
          setGenerationSlots(slots => slots.map((slot, slotIndex) =>
            slotIndex === index
              ? {...slot, status: 'completed', url: generated.url}
              : slot
          ));
          setGenerationProgress(Math.round(((index + 1) / selectedPrompts.length) * 100));
        }
        if (!made.length) throw new Error(job.error_message || job.images.find(image => image.error_message)?.error_message || 'Image generation failed.');
        setResults(made);
        setSelected(made.map(image => image.id));
        setJobs(current => [job, ...current.filter(item => item.id !== job.id)]);
        setAccount(await api.me());
      } else {
        await new Promise(resolve => setTimeout(resolve, 1500));
        const made = generatedImages.slice(0, selectedPromptCount).map((url, index) => ({id: index + 1, url, status: 'completed'}));
        setResults(made);
        setSelected(made.map(image => image.id));
        setAccount(value => ({...value, credits_balance: value.credits_balance - selectedPromptCount}));
      }
      setGenerationProgress(100);
      setGenerationMessage('Your image set is ready to review.');
      setStep(5);
    } catch (error) { setToast(error.message); setStep(3); }
    finally { setBusy(false); }
  }

  async function finish() {
    setBusy(true);
    try {
      if (demo) {
        const job = {id: Date.now(), product, status: 'completed', created_at: new Date().toISOString(), credits_used: selectedPromptCount, images: results.filter(i => selected.includes(i.id))};
        setJobs(current => [job, ...current]);
        setToast('Demo complete — connect Shopify to publish these images.');
      } else {
        const job = await api.addToShopify(jobId, selected);
        setJobs(current => [job, ...current.filter(item => item.id !== job.id)]);
        setToast('Images added to your Shopify product.');
      }
      setTimeout(() => navigate(shopifyTo('/history')), 1000);
    } catch (error) { setToast(error.message); }
    finally { setBusy(false); }
  }

  function openImagePreview(images, index = 0) {
    setLightboxImages(images);
    setLightboxIndex(index);
  }

  if (productLoading) {
    return <div className="page"><div className="catalog-loading"><span className="loading-orb">✦</span><div><strong>{productId ? 'Loading your selected product' : 'Loading products from Shopify'}</strong><small>Preparing your image workspace…</small></div></div></div>;
  }

  if (!product) {
    return <div className="page"><section className="load-error"><span>!</span><div><h2>We couldn’t find a product</h2><p>{productError || 'No products are currently available in this Shopify store.'}</p></div><div className="load-error-actions"><Button onClick={() => setLoadAttempt(value => value + 1)}>Try again</Button><Button variant="primary" onClick={() => navigate(shopifyTo('/products'))}>Browse Shopify products</Button></div></section></div>;
  }

  return <div className="page wizard-page">
    <PageHeader eyebrow="PRODUCT IMAGING" title={step === 1 ? 'Start with a product' : product.title} description="Build a cohesive set of product images in a few focused steps." />
    <div className="stepper">{['Product', 'References', 'Directions', 'Generating', 'Review'].map((label, i) => <div className={step >= i + 1 ? 'step active' : 'step'} key={label}><span>{step > i + 1 ? '✓' : i + 1}</span><small>{label}</small></div>)}</div>
    {step === 1 && <section className="wizard-card">
      <span className="eyebrow">STEP 1 OF 5</span><h2>What are we photographing?</h2>
      <div className="compact-products">{products.map(item => <button className={product.id === item.id ? 'compact-product selected' : 'compact-product'} onClick={() => chooseProduct(item)} key={item.id}>{item.images?.[0]?.url ? <img src={item.images[0].url} alt="" /> : <span className="image-placeholder">No image</span>}<span><strong>{item.title}</strong><small>{item.vendor} · {item.product_type}</small></span><b>{product.id === item.id ? '✓' : ''}</b></button>)}</div>
      <div className="wizard-actions"><span /><Button variant="primary" onClick={() => setStep(2)}>Continue →</Button></div>
    </section>}
    {step === 2 && <section className="wizard-card">
      <span className="eyebrow">STEP 2 OF 5</span><h2>Choose your references</h2><p className="lead">We’ll use these to keep shape, color, materials and branding faithful.</p>
      {product.images?.length ? <div className="reference-grid">{product.images.map((image, i) => <button onClick={() => setReferences(current => current.includes(i) ? current.filter(x => x !== i) : [...current, i])} className={references.includes(i) ? 'reference selected' : 'reference'} key={image.url}><img src={image.url} alt="" /><span>{references[0] === i ? '★ Primary reference' : references.includes(i) ? '✓ Selected' : 'Select'}</span></button>)}</div> : <Banner tone="warning">This product has no images. Creative directions can still be generated, but product details cannot be preserved from a reference.</Banner>}
      <div className="wizard-actions"><Button onClick={() => setStep(1)}>Back</Button><Button variant="primary" loading={busy} onClick={createPrompts}>Build creative directions ✦</Button></div>
    </section>}
    {step === 3 && <section className="wizard-card wide">
      <div className="prompt-heading">
        <div><span className="eyebrow">STEP 3 OF 5</span><h2>Choose your ideas</h2><p className="lead">Select the scenes you want to create. Open any card to edit the full prompt.</p></div>
        <div className="prompt-heading-actions">
          <Button onClick={() => openPromptEditor()}>＋ Add custom prompt</Button>
          <Checkbox label="Select all" checked={allPromptsSelected} onChange={toggleAllPrompts} />
        </div>
      </div>
      <div className="prompt-summary"><span>{selectedPromptCount} of {prompts.length} selected</span><div className="credit-cost">{selectedPromptCount} images · {selectedPromptCount} credits</div></div>
      <div className="prompt-list">{prompts.map((item, index) => {
        const preview = promptText(item.prompt);
        return <article className={item.is_selected ? 'prompt selected' : 'prompt'} key={item.id ?? `custom-${index}`}>
          <button className="prompt-card-copy" onClick={() => togglePrompt(index)} aria-pressed={item.is_selected}>
            <span className="prompt-number">IDEA {String(index + 1).padStart(2, '0')}</span>
            <h3>{item.title || promptTitle(item.prompt, index)}</h3>
            <p>{preview}</p>
          </button>
          <div className="prompt-card-actions">
            <button className="prompt-edit" onClick={() => openPromptEditor(index)} aria-label={`Edit idea ${index + 1}`}>✎ <span>Edit</span></button>
            <button className="prompt-select" onClick={() => togglePrompt(index)} aria-label={`${item.is_selected ? 'Deselect' : 'Select'} idea ${index + 1}`}>
              <span>{item.is_selected ? '✓' : ''}</span>{item.is_selected ? 'Selected' : 'Select'}
            </button>
          </div>
        </article>;
      })}</div>
      <div className="wizard-actions"><Button onClick={() => setStep(2)}>Back</Button><Button variant="primary" disabled={!selectedPromptCount} onClick={createImages}>Generate {selectedPromptCount} images ✦</Button></div>
    </section>}
    {step === 4 && <section className="wizard-card wide">
      <div className="panel-title"><div><span className="eyebrow">STEP 5 OF 5 · GENERATING</span><h2>Your new image set</h2><p className="lead">{generationMessage}</p></div><Badge>{generationSlots.filter(slot => slot.status === 'completed').length} of {generationSlots.length} ready</Badge></div>
      <div className="result-grid">{generationSlots.map((slot, index) =>
        <button className={`result generation-result ${slot.status}`} key={slot.key} disabled>
          {slot.url
            ? <img src={slot.url} alt={`Generated composition ${index + 1}`} />
            : <div className="generation-placeholder"><span className="generation-spinner" /><small>{slot.status === 'failed' ? 'Generation failed' : slot.status === 'processing' ? 'Generating…' : 'Waiting…'}</small></div>}
          <span>{slot.status === 'completed' ? '✓' : String(index + 1).padStart(2, '0')}</span>
        </button>
      )}</div>
      <div className="generation-progress"><ProgressBar progress={generationProgress} tone="success" /><small>{selectedPromptCount} compositions · please keep this page open</small></div>
      <div className="wizard-actions generation-disabled-actions"><Button disabled>Refine directions</Button><Button variant="primary" disabled>Add to product →</Button></div>
    </section>}
    {step === 5 && <section className="wizard-card wide">
      <div className="panel-title"><div><span className="eyebrow">STEP 5 OF 5</span><h2>Your new image set</h2><p className="lead">Select the strongest images to add to Shopify.</p></div><Badge tone="success">{selected.length} selected</Badge></div>
      <div className="result-grid">{results.map((image, index) => <div className={selected.includes(image.id) ? 'result selected' : 'result'} key={image.id}>
        <button type="button" className="result-media" onClick={() => openImagePreview(results.map(item => ({url: item.url})), index)}>
          <img src={image.url} alt={`Generated review ${index + 1}`} />
        </button>
        <span>{selected.includes(image.id) ? '✓' : ''}</span>
        <div className="result-actions">
          <button type="button" className="result-action-button" onClick={event => {
            event.stopPropagation();
            setSelected(current => current.includes(image.id) ? current.filter(x => x !== image.id) : [...current, image.id]);
          }}>Select</button>
          <button type="button" className="result-action-button" onClick={event => {
            event.stopPropagation();
            openImagePreview(results.map(item => ({url: item.url})), index);
          }}>Preview</button>
        </div>
      </div>)}</div>
      <div className="wizard-actions"><Button onClick={() => setStep(3)}>Refine directions</Button><Button variant="primary" loading={busy} disabled={!selected.length} onClick={finish}>Add {selected.length} to product →</Button></div>
    </section>}
    {toast && <Toast content={toast} onDismiss={() => setToast('')} />}
    <ImageLightbox images={lightboxImages} initialIndex={lightboxIndex} onClose={() => {setLightboxIndex(null); setLightboxImages([]);}} />
    {promptEditor && <PromptEditor
      editor={promptEditor}
      onChange={value => setPromptEditor(current => ({...current, value, error: ''}))}
      onSave={savePrompt}
      onClose={() => setPromptEditor(null)}
    />}
  </div>;
}

function History({jobs}) {
  const [openJob, setOpenJob] = useState(null);
  const [lightboxImages, setLightboxImages] = useState([]);
  const [lightboxIndex, setLightboxIndex] = useState(null);

  function openImagePreview(images, index = 0) {
    setLightboxImages(images);
    setLightboxIndex(index);
  }

  return <div className="page"><PageHeader eyebrow="YOUR ARCHIVE" title="Generation history" description="Every creative set, ready to revisit." action={<Button variant="primary" url={shopifyTo('/generate')}>New generation</Button>} />
    {jobs.length ? <div className="history-grid">{jobs.map(job => <article className="history-card" key={job.id}><div className="history-images">{job.images?.slice(0, 3).map(image => <img src={image.url} key={image.id} />)}</div><div className="history-copy"><div><span className="eyebrow">{new Date(job.created_at).toLocaleDateString()}</span><h3>{job.product.title}</h3><small>{job.images?.length} images · {job.credits_used} credits</small></div><Button onClick={() => setOpenJob(job)}>Open set</Button></div></article>)}</div> : <EmptyState heading="No generations yet" action={{content: 'Create images', url: '/generate'}} />}
    {openJob && <div className="prompt-modal-backdrop" onMouseDown={event => {
      if (event.target === event.currentTarget) setOpenJob(null);
    }}>
      <section className="prompt-modal history-set-modal" role="dialog" aria-modal="true" aria-labelledby="history-set-title">
        <header><div><span className="eyebrow">{new Date(openJob.created_at).toLocaleDateString()}</span><h2 id="history-set-title">{openJob.product.title}</h2></div><button className="prompt-modal-close" onClick={() => setOpenJob(null)} aria-label="Close image set">×</button></header>
        <p>{openJob.images?.length || 0} generated images · {openJob.credits_used} credits used</p>
        <div className="history-set-grid">{openJob.images?.filter(image => image.url).map((image, index) =>
          <button type="button" className="history-set-image" key={image.id} onClick={() => openImagePreview(openJob.images.filter(item => item.url).map(item => ({url: item.url})), index)}>
            <img src={image.url} alt="" />
            <span>{image.status}</span>
          </button>
        )}</div>
      </section>
    </div>}
    <ImageLightbox images={lightboxImages} initialIndex={lightboxIndex} onClose={() => {setLightboxIndex(null); setLightboxImages([]);}} />
  </div>;
}

function Billing({account, setAccount}) {
  const fallbackPlans = [
    {id: 'free', name: 'Free', price: 0, credits: 10}, {id: 'starter', name: 'Starter', price: 9, credits: 60},
    {id: 'pro', name: 'Pro', price: 29, credits: 200}, {id: 'growth', name: 'Growth', price: 79, credits: 550},
  ];
  const fallbackPacks = [
    {id: 'boost-50', name: 'Quick boost', price: 9, credits: 50},
    {id: 'boost-150', name: 'Campaign pack', price: 25, credits: 150},
    {id: 'boost-500', name: 'Catalog pack', price: 75, credits: 500},
  ];
  const [plans, setPlans] = useState(fallbackPlans);
  const [packs, setPacks] = useState(fallbackPacks);
  const [busyPlan, setBusyPlan] = useState('');
  const [busyPack, setBusyPack] = useState('');
  const [toast, setToast] = useState('');
  useEffect(() => {
    if (!demoMode) api.plans().then(result => {
      setPlans(result.plans);
      setPacks(result.credit_packs);
    }).catch(error => setToast(error.message));
  }, []);
  useEffect(() => {
    if (demoMode) return;
    const current = new URLSearchParams(location.search);
    const reference = current.get('credit_purchase');
    if (!reference) return;
    api.confirmCreditPurchase(reference).then(result => {
      setAccount(accountState => ({
        ...accountState,
        credits_balance: result.credits_balance,
        purchased_credits_balance: result.purchased_credits_balance,
      }));
      if (result.credited) {
        setToast('Your purchased credits have been added.');
      } else {
        setToast(`Shopify purchase status: ${result.status.toLowerCase()}.`);
      }
    }).catch(error => setToast(error.message)).finally(() => {
      current.delete('credit_purchase');
      const query = current.toString();
      history.replaceState({}, '', `${location.pathname}${query ? `?${query}` : ''}`);
    });
  }, [setAccount]);
  async function choosePlan(plan) {
    setBusyPlan(plan.id);
    try {
      const result = await api.subscribe(plan.id);
      window.open(result.confirmation_url, '_top');
    } catch (error) { setToast(error.message); setBusyPlan(''); }
  }
  async function buyCredits(pack) {
    setBusyPack(pack.id);
    try {
      const result = await api.purchaseCredits(pack.id);
      window.open(result.confirmation_url, '_top');
    } catch (error) { setToast(error.message); setBusyPack(''); }
  }
  return <div className="page"><PageHeader eyebrow="PLAN & CREDITS" title="Room to keep creating" description={`You have ${account.credits_balance} credits left in this billing cycle.`} />
    <Banner title="Credits are only used for completed images" tone="info">Failed generations are automatically refunded to your balance.</Banner>
    <div className="credit-balances">
      <span><b>{account.plan_credits_balance ?? account.credits_balance}</b> plan credits</span>
      <span><b>{account.purchased_credits_balance ?? 0}</b> purchased credits that roll over</span>
    </div>
    <div className="plan-grid">{plans.map(plan => {
      const current = account.plan?.toLowerCase() === (plan.id || plan.name).toLowerCase();
      return <article className={current ? 'plan featured' : 'plan'} key={plan.id || plan.name}>{current && <span className="popular">CURRENT PLAN</span>}<span className="eyebrow">{plan.name}</span><div className="price"><strong>${plan.price}</strong><small>/ month</small></div><p><b>{plan.credits}</b> image credits each month</p><ul><li>All creative directions</li><li>High-resolution exports</li><li>Shopify product publishing</li></ul><Button variant={current ? 'primary' : 'secondary'} fullWidth loading={busyPlan === plan.id} disabled={current || !plan.price || demoMode} onClick={() => choosePlan(plan)}>{current ? 'Your current plan' : plan.price ? 'Choose plan' : 'Free plan'}</Button></article>;
    })}</div>
    <section className="credit-packs">
      <div>
        <span className="eyebrow">ONE-TIME TOP-UP</span>
        <h2>Need a few more images?</h2>
        <p>Purchased credits are added after Shopify confirms payment and do not reset with your monthly plan.</p>
      </div>
      <div className="credit-pack-grid">{packs.map(pack =>
        <article className="credit-pack" key={pack.id}>
          <div><span className="eyebrow">{pack.name}</span><strong>{Number(pack.credits).toLocaleString()} credits</strong></div>
          <Button loading={busyPack === pack.id} disabled={demoMode} onClick={() => buyCredits(pack)}>Buy for ${pack.price}</Button>
        </article>
      )}</div>
    </section>
    {toast && <Toast content={toast} onDismiss={() => setToast('')} />}
  </div>;
}

export default App;
