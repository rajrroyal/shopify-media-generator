export const demoProducts = [
  {id: 1, title: 'Aurelia Everyday Tote', vendor: 'Aurelia', product_type: 'Bags', status: 'ACTIVE', images: [{url: 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=1000'}], description: 'Structured vegan leather tote with soft suede lining and brass hardware.', tags: ['bestseller', 'vegan']},
  {id: 2, title: 'Cloudform Runner', vendor: 'Northline', product_type: 'Shoes', status: 'ACTIVE', images: [{url: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=1000'}], description: 'Lightweight everyday sneaker with a sculpted sole and breathable knit upper.', tags: ['new', 'unisex']},
  {id: 3, title: 'Solis Vitamin C Serum', vendor: 'Solis Lab', product_type: 'Skincare', status: 'ACTIVE', images: [{url: 'https://images.unsplash.com/photo-1620916566398-39f1143ab7be?w=1000'}], description: 'Brightening face serum with vitamin C, ferulic acid, and squalane.', tags: ['clean-beauty']},
  {id: 4, title: 'Contour Stoneware Mug', vendor: 'Common Form', product_type: 'Home', status: 'DRAFT', images: [{url: 'https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=1000'}], description: 'Hand-finished stoneware mug with a matte glaze.', tags: ['handmade']},
];

export const promptIdeas = [
  'Premium ecommerce hero shot on warm limestone, soft directional morning light, confident negative space, preserve exact product details.',
  'Bright seamless studio photograph, product centered at a subtle three-quarter angle, crisp natural shadow, luxury catalog finish.',
  'Aspirational city lifestyle scene during golden hour, product naturally in use, editorial composition and authentic movement.',
  'Extreme close-up detail highlighting material grain, stitching and hardware, shallow depth of field, tactile premium mood.',
  'Minimal tonal set using sculptural paper forms and a restrained neutral palette, sophisticated contemporary art direction.',
  'Seasonal summer campaign with dappled sunlight, fresh citrus accents and a relaxed Mediterranean color story.',
];

export const generatedImages = [
  'https://images.unsplash.com/photo-1594223274512-ad4803739b7c?w=1200',
  'https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=1200',
  'https://images.unsplash.com/photo-1566150905458-1bf1fc113f0d?w=1200',
  'https://images.unsplash.com/photo-1591561954557-26941169b49e?w=1200',
  'https://images.unsplash.com/photo-1590874103328-eac38a683ce7?w=1200',
  'https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=1200',
];

export const demoJobs = [
  {id: 'j1', product: demoProducts[0], status: 'completed', created_at: '2026-06-24T10:20:00Z', credits_used: 6, images: generatedImages.slice(0, 4).map((url, i) => ({id: i + 1, url, status: 'completed'}))},
  {id: 'j2', product: demoProducts[2], status: 'completed', created_at: '2026-06-21T08:10:00Z', credits_used: 4, images: generatedImages.slice(2, 5).map((url, i) => ({id: i + 10, url, status: 'completed'}))},
];

