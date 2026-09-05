package in.bizboard.app;

import android.content.Intent;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    // M1-008: singleTask launch mode means a re-opened deep link arrives here,
    // not via a fresh onCreate — without this, the Bridge (and @capacitor/app's
    // appUrlOpen listener) never sees it.
    @Override
    public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
    }
}
