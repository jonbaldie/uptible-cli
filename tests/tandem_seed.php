<?php
// Disposable tandem fixture seed. NOT for production; never run against production data.
// Provisions a local sqlite database + synthetic users for the tandem integration test.
//
// Usage (from the server repo checkout, code/ directory):
//   TANDEM_SERVER_DIR=/path/to/uptible/code DB_DATABASE=/tmp/tandem/db.sqlite \
//     OAUTH_PUBLIC_CLIENT_ID=11111111-1111-4111-8111-111111111111 \
//     php tests/tandem_seed.php
// Requires: generated RSA keys copied to code/storage/oauth-*.key with mode 600,
// APP_KEY, OAUTH_ENABLED=true, OAUTH_ISSUER and OAUTH_AUDIENCE set to the test server origin.
require getenv('TANDEM_SERVER_DIR').'/vendor/autoload.php';
$app = require getenv('TANDEM_SERVER_DIR').'/bootstrap/app.php';
$kernel = $app->make(Illuminate\Contracts\Console\Kernel::class);
$kernel->bootstrap();

use App\Capture;
use App\LifetimeAccess;
use App\Notification;
use App\PurchaseReference;
use App\User;
use Illuminate\Support\Facades\Artisan;
use Laravel\Passport\Client;

Artisan::call('migrate:fresh', ['--force' => true]);
echo Artisan::output();

$clientId = config('oauth.client_id');
Client::create(['id' => $clientId, 'name' => 'Uptible CLI', 'secret' => null,
    'redirect_uris' => ['http://127.0.0.1/callback'], 'grant_types' => ['authorization_code', 'refresh_token'], 'revoked' => false]);

function makeUser(string $name, bool $grant): User
{
    $u = User::create(['name' => $name, 'email' => $name.'@example.test', 'password' => bcrypt('password123'), 'acc' => $name]);
    if ($grant) {
        app(LifetimeAccess::class)->grantVerifiedLifetime($u->id, new PurchaseReference('test', 'purchase-'.$u->id));
    }
    return $u;
}
function makeNotif(User $u, string $msg): Notification
{
    $n = Notification::create(['user_id' => $u->id, 'url_capture' => 'https://example.test/page', 'url_display' => 'https://example.test/page', 'message' => $msg]);
    $n->is_active = true;
    $n->is_draft = false;
    $n->save();
    return $n;
}

$alpha = makeUser('alpha', true);
$bravo = makeUser('bravo', true);
makeUser('charlie', false);
$aNotif = makeNotif($alpha, 'Alpha tandem message');
$bNotif = makeNotif($bravo, 'Bravo tandem message');
Capture::create(['notification_id' => $aNotif->id, 'name' => 'AlphaLeadOne', 'session_id' => 's1']);
Capture::create(['notification_id' => $bNotif->id, 'name' => 'BravoLeadOne', 'session_id' => 's3']);
echo "SEED OK\n";
