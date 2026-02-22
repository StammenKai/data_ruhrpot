<?php
/**
 * Plugin Name: CR Affiliate Dashboard
 * Plugin URI:  https://ruhrfinds.de
 * Description: Lädt Trend- und Affiliate-Daten direkt von GitHub. Kein FTP, keine lokalen Pfade.
 * Version:     2.0.0
 * Author:      StammenMedia
 * License:     GPL2
 */

defined('ABSPATH') or die('Kein direkter Zugriff.');
define('CR_VERSION', '2.0.0');
define('CR_PLUGIN_URL', plugin_dir_url(__FILE__));

// ═══════════════════════════════════════════════════════════════
// EINSTELLUNGEN
// ═══════════════════════════════════════════════════════════════

function cr_settings(): array {
    return wp_parse_args(get_option('cr_settings', []), [
        'github_user'   => '',
        'github_repo'   => '',
        'github_branch' => 'main',
        'github_token'  => '',
        'cache_minutes' => 60,
    ]);
}

function cr_raw_url(string $path): string {
    $s = cr_settings();
    if (!$s['github_user'] || !$s['github_repo']) return '';
    return "https://raw.githubusercontent.com/{$s['github_user']}/{$s['github_repo']}/{$s['github_branch']}/{$path}";
}

// ═══════════════════════════════════════════════════════════════
// GITHUB DATEN LADEN (mit Cache)
// ═══════════════════════════════════════════════════════════════

function cr_fetch(string $path): ?string {
    $s   = cr_settings();
    $key = 'cr_' . md5($path);
    $hit = get_transient($key);
    if ($hit !== false) return $hit;

    $url  = cr_raw_url($path);
    if (!$url) return null;

    $args = ['timeout' => 15, 'headers' => ['User-Agent' => 'WordPress-CRDashboard/2.0']];
    if ($s['github_token']) $args['headers']['Authorization'] = 'token ' . $s['github_token'];

    $resp = wp_remote_get($url, $args);
    if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return null;

    $body = wp_remote_retrieve_body($resp);
    set_transient($key, $body, (int)$s['cache_minutes'] * 60);
    return $body;
}

// GitHub API: Dateiliste eines Ordners abrufen
function cr_list_dir(string $dir): array {
    $s   = cr_settings();
    $key = 'cr_dir_' . md5($dir);
    $hit = get_transient($key);
    if ($hit !== false) return $hit;

    $url  = "https://api.github.com/repos/{$s['github_user']}/{$s['github_repo']}/contents/{$dir}";
    $args = ['timeout' => 15, 'headers' => ['User-Agent' => 'WordPress-CRDashboard/2.0']];
    if ($s['github_token']) $args['headers']['Authorization'] = 'token ' . $s['github_token'];

    $resp = wp_remote_get($url, $args);
    if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return [];

    $list = json_decode(wp_remote_retrieve_body($resp), true) ?? [];
    set_transient($key, $list, (int)$s['cache_minutes'] * 60);
    return $list;
}

function cr_clear_cache(): void {
    global $wpdb;
    $wpdb->query("DELETE FROM {$wpdb->options} WHERE option_name LIKE '_transient_cr_%' OR option_name LIKE '_transient_timeout_cr_%'");
}

// ═══════════════════════════════════════════════════════════════
// DATEN PARSEN
// ═══════════════════════════════════════════════════════════════

function cr_latest_file(string $dir, string $prefix, string $ext): ?string {
    $files = array_filter(cr_list_dir($dir), fn($f) =>
        isset($f['name']) &&
        str_starts_with($f['name'], $prefix) &&
        str_ends_with($f['name'], $ext)
    );
    if (!$files) return null;
    usort($files, fn($a, $b) => strcmp($b['name'], $a['name']));
    return reset($files)['name'];
}

function cr_load_summary(): array {
    $file = cr_latest_file('output', 'summary_', '.json');
    if ($file) {
        $body = cr_fetch("output/{$file}");
        if ($body) { $data = json_decode($body, true); if ($data) return $data; }
    }
    return cr_demo_summary();
}

function cr_load_trends(): array {
    $file = cr_latest_file('output', 'affiliate_chancen_', '.csv');
    if ($file) {
        $body = cr_fetch("output/{$file}");
        if ($body) {
            $rows   = array_map('str_getcsv', explode("\n", trim($body)));
            $header = array_shift($rows);
            $result = [];
            foreach ($rows as $row) {
                if ($header && count($row) === count($header)) $result[] = array_combine($header, $row);
            }
            if ($result) return $result;
        }
    }
    return cr_demo_trends();
}

function cr_load_articles(): array {
    $body = cr_fetch('content_log.json');
    if ($body) { $data = json_decode($body, true); if ($data) return $data; }
    return cr_demo_articles();
}

function cr_load_osm(): array {
    $file = cr_latest_file('output', 'osm_', '.csv');
    if ($file) {
        $body = cr_fetch("output/{$file}");
        if ($body) {
            $rows   = array_map('str_getcsv', explode("\n", trim($body)));
            $header = array_shift($rows);
            $cats   = [];
            foreach ($rows as $row) {
                if ($header && count($row) >= count($header)) {
                    $d   = array_combine($header, array_slice($row, 0, count($header)));
                    $cat = $d['kategorie'] ?? 'Unbekannt';
                    $cats[$cat] = ($cats[$cat] ?? 0) + 1;
                }
            }
            if ($cats) return $cats;
        }
    }
    return cr_demo_osm();
}

// ═══════════════════════════════════════════════════════════════
// DEMO-DATEN
// ═══════════════════════════════════════════════════════════════

function cr_demo_summary(): array {
    return ['datum'=>date('Y-m-d'),'osm_gesamt'=>342,'osm_laeden'=>128,'osm_gastronomie'=>87,'osm_freizeit'=>63,'events_gesamt'=>14,'bevoelkerung_aktuell'=>71500,'_demo'=>true];
}
function cr_demo_trends(): array {
    return [
        ['gruppe'=>'Fahrrad & Outdoor',    'trend'=>'steigend ↑','affiliate_score'=>78,'veraenderung_%'=>12.3,'empfohlene_partner'=>'Decathlon, Amazon'],
        ['gruppe'=>'Heimwerken & Garten',  'trend'=>'stabil →',  'affiliate_score'=>65,'veraenderung_%'=>2.1, 'empfohlene_partner'=>'OBI, Hornbach'],
        ['gruppe'=>'Elektronik & Technik', 'trend'=>'steigend ↑','affiliate_score'=>61,'veraenderung_%'=>8.7, 'empfohlene_partner'=>'Amazon, MediaMarkt'],
        ['gruppe'=>'Gesundheit & Fitness', 'trend'=>'stabil →',  'affiliate_score'=>54,'veraenderung_%'=>1.2, 'empfohlene_partner'=>'Myprotein, SportScheck'],
        ['gruppe'=>'Familie & Kinder',     'trend'=>'fallend ↓', 'affiliate_score'=>38,'veraenderung_%'=>-4.5,'empfohlene_partner'=>'Amazon, myToys'],
        ['gruppe'=>'Mode & Lifestyle',     'trend'=>'stabil →',  'affiliate_score'=>35,'veraenderung_%'=>0.8, 'empfohlene_partner'=>'Zalando, AboutYou'],
    ];
}
function cr_demo_articles(): array {
    return [['datum'=>date('Y-m-d'),'titel'=>'E-Bikes im Ruhrgebiet – Demo','gruppe'=>'Fahrrad & Outdoor','wortanzahl'=>1820,'wp_status'=>'draft','wp_url'=>'#']];
}
function cr_demo_osm(): array {
    return ['Laden/Geschäft'=>128,'Gastronomie/Service'=>87,'Freizeit'=>63,'Tourismus'=>14];
}

// ═══════════════════════════════════════════════════════════════
// HOOKS
// ═══════════════════════════════════════════════════════════════

add_action('admin_menu', function() {
    add_menu_page('CR Dashboard','📊 CR Dashboard','manage_options','cr-dashboard','cr_page_dashboard','dashicons-chart-area',3);
    add_submenu_page('cr-dashboard','Übersicht',      'Übersicht',      'manage_options','cr-dashboard','cr_page_dashboard');
    add_submenu_page('cr-dashboard','Trends',         'Trends',         'manage_options','cr-trends',  'cr_page_trends');
    add_submenu_page('cr-dashboard','Artikel-Log',    'Artikel-Log',    'manage_options','cr-articles','cr_page_articles');
    add_submenu_page('cr-dashboard','⚙️ GitHub Setup','⚙️ GitHub Setup','manage_options','cr-settings','cr_page_settings');
});

add_action('admin_init', function() {
    register_setting('cr_group', 'cr_settings', ['sanitize_callback' => function($i) {
        return [
            'github_user'   => sanitize_text_field($i['github_user']   ?? ''),
            'github_repo'   => sanitize_text_field($i['github_repo']   ?? ''),
            'github_branch' => sanitize_text_field($i['github_branch'] ?? 'main'),
            'github_token'  => sanitize_text_field($i['github_token']  ?? ''),
            'cache_minutes' => absint($i['cache_minutes'] ?? 60),
        ];
    }]);
});

add_action('admin_enqueue_scripts', function($hook) {
    if (!str_contains($hook, 'cr-') && $hook !== 'toplevel_page_cr-dashboard') return;
    wp_enqueue_script('chartjs', 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js', [], '4.4.0', true);
    wp_add_inline_script('chartjs', cr_js(), 'after');
    wp_localize_script('chartjs', 'crCfg', [
        'ajax'  => admin_url('admin-ajax.php'),
        'nonce' => wp_create_nonce('cr_nonce'),
    ]);
});

add_action('wp_ajax_cr_data', function() {
    check_ajax_referer('cr_nonce', 'nonce');
    match(sanitize_text_field($_GET['type'] ?? '')) {
        'summary'  => wp_send_json_success(cr_load_summary()),
        'trends'   => wp_send_json_success(cr_load_trends()),
        'articles' => wp_send_json_success(cr_load_articles()),
        'osm'      => wp_send_json_success(cr_load_osm()),
        default    => wp_send_json_error('Unbekannt'),
    };
});

add_action('wp_ajax_cr_clear_cache', function() {
    check_ajax_referer('cr_nonce', 'nonce');
    if (current_user_can('manage_options')) { cr_clear_cache(); wp_send_json_success(); }
});

// ═══════════════════════════════════════════════════════════════
// SEITEN
// ═══════════════════════════════════════════════════════════════

function cr_page_dashboard() {
    $s    = cr_settings();
    $ok   = $s['github_user'] && $s['github_repo'];
    ?>
<div class="wrap cr-wrap">
<div class="cr-header">
    <div>
        <h1>📊 CR Affiliate Dashboard</h1>
        <span class="cr-sub">Castrop-Rauxel · <?= date('d.m.Y') ?></span>
    </div>
    <div style="display:flex;gap:.6rem;align-items:center">
        <?php if (!$ok): ?>
            <a href="<?= admin_url('admin.php?page=cr-settings') ?>" class="button button-primary">⚙️ GitHub verbinden</a>
        <?php else: ?>
            <span style="color:#22c55e;font-size:.85rem">● <?= esc_html($s['github_user'].'/'.$s['github_repo']) ?></span>
            <button class="button" onclick="CR.clearCache()">🗑 Cache leeren</button>
        <?php endif; ?>
        <button class="button" onclick="CR.init()">⟳ Neu laden</button>
    </div>
</div>

<?php if (!$ok): ?>
<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:1.2rem;margin-bottom:1rem">
    <strong>⚠️ GitHub noch nicht verbunden.</strong>
    Bitte zuerst <a href="<?= admin_url('admin.php?page=cr-settings') ?>"><strong>GitHub Setup</strong></a> öffnen und Username + Repository eintragen.
    Danach werden hier echte Daten von deinem Workflow angezeigt.
</div>
<?php endif; ?>

<div class="cr-kpi-grid" id="cr-kpis"><div class="cr-kpi">Lade...</div></div>

<div class="cr-2col">
    <div class="cr-card"><div class="cr-ch">🏪 Einrichtungen</div><canvas id="chartOsm" height="220"></canvas></div>
    <div class="cr-card"><div class="cr-ch">🏆 Affiliate-Scores</div><canvas id="chartAff" height="220"></canvas></div>
</div>

<div class="cr-card">
    <div class="cr-ch">📈 Trend-Übersicht</div>
    <table class="cr-table" id="cr-trend-table">
        <thead><tr><th>Kategorie</th><th>Trend</th><th>Veränderung</th><th>Score</th><th>Partner</th></tr></thead>
        <tbody><tr><td colspan="5" class="cr-empty">Lade von GitHub...</td></tr></tbody>
    </table>
</div>

<div class="cr-card">
    <div class="cr-ch">📝 Zuletzt generierte Artikel</div>
    <table class="cr-table" id="cr-art-table">
        <thead><tr><th>Datum</th><th>Titel</th><th>Thema</th><th>Wörter</th><th>Status</th><th>Link</th></tr></thead>
        <tbody><tr><td colspan="6" class="cr-empty">Lade von GitHub...</td></tr></tbody>
    </table>
</div>
</div>
<?php cr_css(); }

function cr_page_trends() { ?>
<div class="wrap cr-wrap">
<div class="cr-header"><h1>📈 Trends & Affiliate</h1></div>
<div class="cr-card">
    <div class="cr-ch">Affiliate-Analyse</div>
    <table class="cr-table" id="cr-trends-table">
        <thead><tr><th>Kategorie</th><th>Trend</th><th>Veränderung</th><th>Score</th><th>Keywords</th><th>Partner</th></tr></thead>
        <tbody><tr><td colspan="6" class="cr-empty">Lade...</td></tr></tbody>
    </table>
</div>
<div class="cr-card">
    <div class="cr-ch">📊 Score-Chart</div>
    <canvas id="chartAffFull" height="120"></canvas>
</div>
</div>
<script>
document.addEventListener('DOMContentLoaded', async () => {
    const r = await fetch(crCfg.ajax + '?action=cr_data&type=trends&nonce=' + crCfg.nonce);
    const d = await r.json();
    if (!d.success) return;
    const data = d.data;

    // Tabelle befüllen
    const tb = document.querySelector('#cr-trends-table tbody');
    tb.innerHTML = data.map(row => {
        const sc = parseFloat(row.affiliate_score);
        const ch = parseFloat(row['veraenderung_%'] || 0);
        const chHtml = ch > 0
            ? `<span class="cr-up">+${ch.toFixed(1)}%</span>`
            : ch < 0 ? `<span class="cr-dn">${ch.toFixed(1)}%</span>`
            : `${ch.toFixed(1)}%`;
        const tMap = {'steigend ↑':'#dcfce7;color:#166534','fallend ↓':'#fee2e2;color:#991b1b','stabil →':'#f1f5f9;color:#475569'};
        const tc = tMap[row.trend] || tMap['stabil →'];
        const bar = `<div class="cr-bar"><div class="cr-bar-bg"><div class="cr-bar-f" style="width:${sc}%;background:${sc>=70?'#22c55e':sc>=50?'#f59e0b':'#ef4444'}"></div></div><span class="cr-bar-n">${sc.toFixed(0)}</span></div>`;
        return `<tr>
            <td><strong>${row.gruppe}</strong></td>
            <td><span class="cr-badge" style="background:${tc}">${row.trend}</span></td>
            <td>${chHtml}</td>
            <td>${bar}</td>
            <td style="font-size:.75rem;color:#64748b">${row.keywords || '–'}</td>
            <td style="font-size:.75rem;color:#64748b">${row.empfohlene_partner || '–'}</td>
        </tr>`;
    }).join('');

    // Chart
    const sorted = [...data].sort((a,b) => b.affiliate_score - a.affiliate_score);
    new Chart(document.getElementById('chartAffFull'), {
        type: 'bar',
        data: {
            labels: sorted.map(x => x.gruppe),
            datasets: [{
                data: sorted.map(x => parseFloat(x.affiliate_score)),
                backgroundColor: sorted.map(x => parseFloat(x.affiliate_score) >= 70 ? '#22c55e' : parseFloat(x.affiliate_score) >= 50 ? '#f59e0b' : '#ef4444'),
                borderRadius: 5, borderSkipped: false
            }]
        },
        options: {
            indexAxis: 'y', responsive: true,
            plugins: { legend: { display: false } },
            scales: { x: { max: 100 }, y: { grid: { display: false } } }
        }
    });
});
</script>
<?php cr_css(); }

function cr_page_articles() { ?>
<div class="wrap cr-wrap">
<div class="cr-header"><h1>📝 Artikel-Protokoll</h1></div>
<div class="cr-card">
    <div class="cr-ch">Alle KI-Artikel</div>
    <table class="cr-table" id="cr-full-art">
        <thead><tr><th>Datum</th><th>Titel</th><th>Thema</th><th>Wörter</th><th>Status</th><th>Link</th></tr></thead>
        <tbody><tr><td colspan="6" class="cr-empty">Lade...</td></tr></tbody>
    </table>
</div>
</div>
<?php cr_css(); }

function cr_page_settings() {
    $s = cr_settings();

    // Verbindungstest nach Speichern
    $status = '';
    if ($s['github_user'] && $s['github_repo']) {
        $url  = "https://api.github.com/repos/{$s['github_user']}/{$s['github_repo']}";
        $args = ['timeout'=>10,'headers'=>['User-Agent'=>'WordPress-CRDashboard']];
        if ($s['github_token']) $args['headers']['Authorization'] = 'token '.$s['github_token'];
        $resp = wp_remote_get($url, $args);
        $code = is_wp_error($resp) ? 0 : wp_remote_retrieve_response_code($resp);
        $status = $code === 200 ? 'ok' : ($code === 404 ? 'notfound' : 'error');
    }
    ?>
<div class="wrap">
<h1>⚙️ GitHub Setup</h1>

<?php if ($status === 'ok'): ?>
<div class="notice notice-success inline"><p>✅ Verbunden mit <strong><?= esc_html($s['github_user'].'/'.$s['github_repo']) ?></strong> – Daten werden direkt von GitHub geladen.</p></div>
<?php elseif ($status === 'notfound'): ?>
<div class="notice notice-error inline"><p>❌ Repository nicht gefunden. Username oder Repository-Name prüfen.</p></div>
<?php elseif ($status === 'error'): ?>
<div class="notice notice-error inline"><p>❌ Verbindung fehlgeschlagen. Evtl. Access Token nötig (privates Repo)?</p></div>
<?php endif; ?>

<form method="post" action="options.php" style="max-width:680px;margin-top:1.5rem">
<?php settings_fields('cr_group'); ?>

<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:1.5rem;margin-bottom:1rem">
<h3 style="margin:0 0 1.2rem;font-size:1rem;padding-bottom:.6rem;border-bottom:1px solid #f1f5f9">🐙 GitHub Repository</h3>
<table class="form-table">
<tr>
    <th scope="row">GitHub Username</th>
    <td>
        <input type="text" name="cr_settings[github_user]" value="<?= esc_attr($s['github_user']) ?>" placeholder="z.B. maxmustermann" class="regular-text">
        <p class="description">Dein GitHub-Benutzername (wie er in der URL steht)</p>
    </td>
</tr>
<tr>
    <th scope="row">Repository Name</th>
    <td>
        <input type="text" name="cr_settings[github_repo]" value="<?= esc_attr($s['github_repo']) ?>" placeholder="z.B. data_ruhrpot" class="regular-text">
        <p class="description">Exakter Name des Repositories – so wie er auf GitHub heißt</p>
    </td>
</tr>
<tr>
    <th scope="row">Branch</th>
    <td>
        <input type="text" name="cr_settings[github_branch]" value="<?= esc_attr($s['github_branch']) ?>" placeholder="main" class="regular-text">
        <p class="description">Standard: <code>main</code></p>
    </td>
</tr>
<tr>
    <th scope="row">Access Token <em style="font-weight:400">(optional)</em></th>
    <td>
        <input type="password" name="cr_settings[github_token]" value="<?= esc_attr($s['github_token']) ?>" placeholder="ghp_xxxxxxxxxxxx" class="regular-text" autocomplete="new-password">
        <p class="description">
            Nur nötig wenn das Repository <strong>privat</strong> ist.<br>
            <a href="https://github.com/settings/tokens/new?scopes=repo&description=CR-Dashboard" target="_blank">→ Token hier erstellen</a> (Haken bei <code>repo</code> setzen)
        </p>
    </td>
</tr>
<tr>
    <th scope="row">Cache-Dauer</th>
    <td>
        <input type="number" name="cr_settings[cache_minutes]" value="<?= esc_attr($s['cache_minutes']) ?>" min="5" max="1440" class="small-text"> Minuten
        <p class="description">Wie lange Daten aus GitHub zwischengespeichert werden (empfohlen: 60)</p>
    </td>
</tr>
</table>
</div>

<?php if ($s['github_user'] && $s['github_repo']): ?>
<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:1.2rem;margin-bottom:1.2rem;font-size:.85rem">
    <strong>📡 Daten werden geladen von:</strong>
    <div style="margin-top:.5rem;display:flex;flex-direction:column;gap:.25rem">
        <code style="color:#166534"><?= esc_html(cr_raw_url('output/summary_' . date('Y-m-d') . '.json')) ?></code>
        <code style="color:#166534"><?= esc_html(cr_raw_url('output/affiliate_chancen_' . date('Y-m-d') . '.csv')) ?></code>
        <code style="color:#166534"><?= esc_html(cr_raw_url('content_log.json')) ?></code>
    </div>
</div>
<?php endif; ?>

<?php submit_button('💾 Speichern & Verbindung testen'); ?>
</form>

<form method="post" style="margin-top:.5rem">
<?php wp_nonce_field('cr_clear'); ?>
<?php if (isset($_POST['cr_do_clear']) && check_admin_referer('cr_clear')): cr_clear_cache(); ?>
<div class="notice notice-success inline" style="margin-bottom:.8rem"><p>✓ Cache geleert.</p></div>
<?php endif; ?>
    <button type="submit" name="cr_do_clear" class="button">🗑 Cache jetzt leeren</button>
    <span style="color:#64748b;font-size:.82rem;margin-left:.5rem">Erzwingt sofortiges Neu-Laden von GitHub beim nächsten Aufruf</span>
</form>
</div>
<?php cr_css(); }

// ═══════════════════════════════════════════════════════════════
// CSS
// ═══════════════════════════════════════════════════════════════

function cr_css() { ?>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap');
.cr-wrap *{box-sizing:border-box;font-family:'DM Sans',sans-serif}.cr-wrap{max-width:1400px;padding:0}
.cr-header{display:flex;align-items:center;justify-content:space-between;padding:1.5rem 0 1rem;border-bottom:2px solid #e2e8f0;margin-bottom:1.5rem}
.cr-header h1{font-size:1.5rem;font-weight:700;color:#0f172a;margin:0;padding:0}
.cr-sub{color:#64748b;font-size:.85rem;margin-left:.6rem}
.cr-kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:1rem}
.cr-kpi{background:#fff;border-radius:10px;padding:1.1rem 1.3rem;box-shadow:0 1px 3px rgba(0,0,0,.06);border:1px solid #f1f5f9}
.cr-kpi-l{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;margin-bottom:.4rem}
.cr-kpi-v{font-size:1.8rem;font-weight:700;color:#0f172a;line-height:1}
.cr-kpi-s{font-size:.75rem;color:#64748b;margin-top:.25rem}
.cr-2col{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem}
.cr-card{background:#fff;border-radius:10px;padding:1.2rem 1.4rem;box-shadow:0 1px 3px rgba(0,0,0,.06);border:1px solid #f1f5f9;margin-bottom:1rem}
.cr-ch{font-size:.88rem;font-weight:600;color:#1e293b;margin-bottom:.8rem;padding-bottom:.5rem;border-bottom:1px solid #f1f5f9}
.cr-table{width:100%;border-collapse:collapse;font-size:.85rem}
.cr-table th{background:#f8fafc;padding:.55rem .85rem;text-align:left;font-weight:600;color:#475569;font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid #e2e8f0}
.cr-table td{padding:.55rem .85rem;border-bottom:1px solid #f8fafc;color:#334155}
.cr-table tr:hover td{background:#fafafa}
.cr-empty{color:#94a3b8;font-style:italic;text-align:center;padding:1.5rem}
.cr-badge{display:inline-block;padding:.18rem .55rem;border-radius:20px;font-size:.7rem;font-weight:600}
.cr-up{color:#16a34a;font-weight:600}.cr-dn{color:#dc2626;font-weight:600}
.cr-bar{display:flex;align-items:center;gap:.4rem}
.cr-bar-bg{flex:1;height:7px;background:#f1f5f9;border-radius:3px;overflow:hidden}
.cr-bar-f{height:100%;border-radius:3px}
.cr-bar-n{font-size:.78rem;font-weight:600;color:#334155;min-width:1.8rem}
.cr-demo{background:#fef9c3;color:#92400e;font-size:.65rem;padding:.1rem .35rem;border-radius:3px;margin-left:.4rem}
@media(max-width:900px){.cr-2col{grid-template-columns:1fr}}
</style>
<?php }

// ═══════════════════════════════════════════════════════════════
// JAVASCRIPT
// ═══════════════════════════════════════════════════════════════

function cr_js(): string { return <<<'JS'
const CR = {
  charts: {},
  async get(type) {
    try {
      const r = await fetch(crCfg.ajax + '?action=cr_data&type=' + type + '&nonce=' + crCfg.nonce);
      const d = await r.json();
      return d.success ? d.data : null;
    } catch(e) { return null; }
  },
  fmt(n) { return new Intl.NumberFormat('de-DE').format(n || 0); },
  color(s) { return s >= 70 ? '#22c55e' : s >= 50 ? '#f59e0b' : '#ef4444'; },
  trend(t) {
    const m = {'steigend ↑':'#dcfce7;color:#166534','fallend ↓':'#fee2e2;color:#991b1b','stabil →':'#f1f5f9;color:#475569'};
    const c = m[t] || m['stabil →'];
    return `<span class="cr-badge" style="background:${c}">${t}</span>`;
  },
  status(s) {
    const m = {publish:'#dcfce7;color:#166534',draft:'#fef9c3;color:#854d0e',private:'#f1f5f9;color:#475569'};
    return `<span class="cr-badge" style="background:${m[s]||m.draft}">${s}</span>`;
  },

  async kpis() {
    const d = await this.get('summary');
    if (!d) return;
    const demo = d._demo ? '<span class="cr-demo">Demo</span>' : '';
    const el = document.getElementById('cr-kpis');
    if (!el) return;
    el.innerHTML = [
      {l:'OSM Einrichtungen', v:this.fmt(d.osm_gesamt),          s:'Gesamt'},
      {l:'Läden & Geschäfte', v:this.fmt(d.osm_laeden),          s:'Einzelhandel'},
      {l:'Gastronomie',       v:this.fmt(d.osm_gastronomie),     s:'Restaurants & Cafés'},
      {l:'Freizeit',          v:this.fmt(d.osm_freizeit),        s:'Sport & Kultur'},
      {l:'Events',            v:this.fmt(d.events_gesamt),       s:'Veranstaltungen'},
      {l:'Einwohner',         v:this.fmt(d.bevoelkerung_aktuell),s:'Stand 2023'},
    ].map(k=>`<div class="cr-kpi"><div class="cr-kpi-l">${k.l}${demo}</div><div class="cr-kpi-v">${k.v}</div><div class="cr-kpi-s">${k.s}</div></div>`).join('');
  },

  async osmChart() {
    const d = await this.get('osm');
    if (!d) return;
    const c = document.getElementById('chartOsm');
    if (!c) return;
    if (this.charts.osm) this.charts.osm.destroy();
    this.charts.osm = new Chart(c, {
      type: 'doughnut',
      data: {labels:Object.keys(d), datasets:[{data:Object.values(d), backgroundColor:['#3b82f6','#f59e0b','#22c55e','#8b5cf6','#ef4444'], borderWidth:0}]},
      options: {responsive:true, plugins:{legend:{position:'bottom'}}, cutout:'60%'}
    });
  },

  async affChart() {
    const d = await this.get('trends');
    if (!d) return;
    const c = document.getElementById('chartAff');
    if (!c) return;
    if (this.charts.aff) this.charts.aff.destroy();
    const sorted = [...d].sort((a,b) => b.affiliate_score - a.affiliate_score);
    this.charts.aff = new Chart(c, {
      type: 'bar',
      data: {
        labels: sorted.map(x=>x.gruppe),
        datasets: [{data:sorted.map(x=>parseFloat(x.affiliate_score)), backgroundColor:sorted.map(x=>this.color(parseFloat(x.affiliate_score))), borderRadius:5, borderSkipped:false}]
      },
      options: {indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{x:{max:100}, y:{grid:{display:false}}}}
    });
    this.trendTable(d);
  },

  trendTable(data) {
    const tb = document.querySelector('#cr-trend-table tbody');
    if (!tb) return;
    tb.innerHTML = data.map(d => {
      const sc = parseFloat(d.affiliate_score);
      const ch = parseFloat(d['veraenderung_%'] || 0);
      const chHtml = ch > 0 ? `<span class="cr-up">+${ch.toFixed(1)}%</span>` : ch < 0 ? `<span class="cr-dn">${ch.toFixed(1)}%</span>` : `${ch.toFixed(1)}%`;
      return `<tr>
        <td><strong>${d.gruppe}</strong></td>
        <td>${this.trend(d.trend)}</td>
        <td>${chHtml}</td>
        <td><div class="cr-bar"><div class="cr-bar-bg"><div class="cr-bar-f" style="width:${sc}%;background:${this.color(sc)}"></div></div><span class="cr-bar-n">${sc.toFixed(0)}</span></div></td>
        <td style="font-size:.78rem;color:#64748b">${d.empfohlene_partner||'–'}</td>
      </tr>`;
    }).join('');
  },

  async articles() {
    const d = await this.get('articles');
    if (!d) return;
    const tb = document.querySelector('#cr-art-table tbody, #cr-full-art tbody');
    if (!tb) return;
    tb.innerHTML = [...d].reverse().slice(0,20).map(a => `<tr>
      <td style="font-family:monospace;font-size:.75rem;color:#94a3b8">${a.datum}</td>
      <td><strong>${(a.titel||'').substring(0,55)}${(a.titel||'').length>55?'…':''}</strong></td>
      <td style="font-size:.78rem;color:#64748b">${a.gruppe||'–'}</td>
      <td style="font-family:monospace;font-size:.8rem">${this.fmt(a.wortanzahl)}</td>
      <td>${this.status(a.wp_status||'draft')}</td>
      <td>${a.wp_url&&a.wp_url!='#'?`<a href="${a.wp_url}" target="_blank" style="color:#2563eb">→ Öffnen</a>`:'–'}</td>
    </tr>`).join('');
  },

  async clearCache() {
    await fetch(crCfg.ajax + '?action=cr_clear_cache&nonce=' + crCfg.nonce);
    this.init();
  },

  async init() {
    await Promise.all([this.kpis(), this.osmChart(), this.affChart(), this.articles()]);
  }
};
document.addEventListener('DOMContentLoaded', () => CR.init());
JS; }
