// Run as a Chrome DevTools Snippet on a Google Maps place with Reviews open.
(async () => {
    const limit = 100;
    const cardSelector = '.jftiEf[data-review-id]';
    const originalLabel = /^(See original|Show original|Lihat asal|Lihat yang asal)$/i;
    const priceLabel = /^(price per person|harga seorang|harga setiap orang|harga per orang)$/i;
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    const source = new URL(location.href);
    source.search = '';
    source.hash = '';
    if (!/^(www\.)?google\.com(\.my)?$/.test(source.hostname) ||
        source.protocol !== 'https:' || !source.pathname.startsWith('/maps/place/')) {
        throw new Error('Open a restaurant listing in Google Maps first.');
    }
    const placeName = () => (document.querySelector('h1.DUwDvf')?.innerText ||
        document.querySelector('main[aria-label], [role="main"][aria-label]')?.getAttribute('aria-label') || '').trim();
    const sourceName = placeName();
    if (!sourceName || !document.querySelector(cardSelector)) {
        throw new Error('Open the Reviews panel and wait for the first reviews to load.');
    }

    const visible = element => Boolean(element?.getClientRects().length);
    const originalButton = card => [...card.querySelectorAll('button')].find(button =>
        visible(button) && originalLabel.test((button.getAttribute('aria-label') || button.innerText).trim()));
    const samePlace = () => location.origin === source.origin &&
        location.pathname === source.pathname && placeName() === sourceName;
    const seen = new Map();
    let idle = 0;
    let reason = 'scroll_limit';
    try {
        for (let round = 0; round < 100; round++) {
            if (!samePlace()) {
                reason = 'place_changed';
                break;
            }
            const cards = [...document.querySelectorAll(cardSelector)];
            const unread = cards.filter(card => !seen.has(card.dataset.reviewId));
            const originalButtons = unread.map(originalButton).filter(Boolean);
            for (const button of originalButtons) button.click();
            if (originalButtons.length) await pause(750);
            if (!samePlace()) {
                reason = 'place_changed';
                break;
            }

            const moreButtons = unread.map(card => card.querySelector('button.w8nwRe')).filter(visible);
            for (const button of moreButtons) button.click();
            if (moreButtons.length) await pause(750);
            if (!samePlace()) {
                reason = 'place_changed';
                break;
            }

            const previousCount = seen.size;
            for (const card of unread) {
                if (!card.isConnected || originalButton(card) ||
                    visible(card.querySelector('button.w8nwRe')) ||
                    /translated by google|diterjemahkan oleh google/i.test(card.innerText)) continue;
                const nodes = card.querySelectorAll('.wiI7pd');
                const raw = nodes.length === 1 ? nodes[0].innerText : '';
                if (!raw.trim()) continue;

                const stars = card.querySelector('[role="img"][aria-label*="star" i], [role="img"][aria-label*="bintang" i]');
                const rating = stars?.getAttribute('aria-label')?.match(/\d+(?:[.,]\d+)?/)?.[0];
                const price = [...card.querySelectorAll('.PBK6be')].find(block =>
                    priceLabel.test(block.firstElementChild?.innerText.trim() || ''));
                seen.set(card.dataset.reviewId, {
                    raw_review: raw,
                    rating: rating ? Number(rating.replace(',', '.')) : null,
                    review_date: card.querySelector('.rsqaWe')?.innerText || null,
                    price_range: price?.children[1]?.innerText.trim() || null,
                    collected_at: new Date().toISOString()
                });
                if (seen.size >= limit) break;
            }
            if (seen.size !== previousCount) console.info('Saved ' + seen.size + ' written reviews');
            if (seen.size >= limit) {
                reason = 'user_limit';
                break;
            }

            idle = seen.size === previousCount ? idle + 1 : 0;
            if (idle >= 5) {
                reason = /seeing a limited view of Google Maps/i.test(document.body.innerText)
                    ? 'limited_view' : 'stalled_unverified';
                break;
            }
            let pane = cards.at(-1)?.parentElement;
            while (pane && (!/(auto|scroll)/.test(getComputedStyle(pane).overflowY) ||
                pane.scrollHeight <= pane.clientHeight)) pane = pane.parentElement;
            if (!pane) {
                reason = 'no_scrollable_review_pane';
                break;
            }
            pane.scrollTop += Math.max(400, pane.clientHeight * 0.8);
            await pause(2500);
        }
    } catch (error) {
        console.error(error);
        reason = 'error';
    }

    if (!seen.size) {
        console.warn('No written reviews collected. Stop reason: ' + reason);
        return;
    }
    const payload = {
        format: 'google-maps-browser-export-v1',
        source_name: sourceName,
        source_url: source.href,
        stop_reason: reason,
        reviews: [...seen.values()]
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'});
    const objectUrl = URL.createObjectURL(blob);
    const download = document.createElement('a');
    download.href = objectUrl;
    download.download = 'google-maps-review-export.json';
    download.click();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
    console.info('Exported ' + seen.size + ' written reviews. Stop reason: ' + reason);
})();
