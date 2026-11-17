package local.realrun.gpsprobe;

import android.app.Activity;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.util.Log;
import android.view.WindowManager;
import android.widget.TextView;

/** Local integration fixture. It has no network permission and no accounts. */
public final class GpsProbe extends Activity implements LocationListener {
    private LocationManager locations;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        TextView text = new TextView(this);
        text.setText("Local GPS integration test");
        setContentView(text);
        locations = (LocationManager) getSystemService(LOCATION_SERVICE);
        try {
            locations.requestLocationUpdates(LocationManager.GPS_PROVIDER, 0, 0, this);
            Log.i("RealRunGPSProbe", "listening");
        } catch (SecurityException error) {
            Log.e("RealRunGPSProbe", "permission missing", error);
        }
    }

    @Override public void onLocationChanged(Location location) {
        Log.i("RealRunGPSProbe", "{\"latitude\":" + location.getLatitude()
            + ",\"longitude\":" + location.getLongitude()
            + ",\"speed\":" + location.getSpeed()
            + ",\"elapsedNanos\":" + location.getElapsedRealtimeNanos()
            + ",\"timeMillis\":" + location.getTime()
            + ",\"provider\":\"" + location.getProvider() + "\"}");
    }

    @Override public void onStatusChanged(String provider, int status, Bundle extra) {}
    @Override public void onProviderEnabled(String provider) {}
    @Override public void onProviderDisabled(String provider) {}

    @Override public void onDestroy() {
        if (locations != null) locations.removeUpdates(this);
        super.onDestroy();
    }
}
