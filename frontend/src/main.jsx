import ReactDOM from 'react-dom/client';
import {AppProvider} from '@shopify/polaris';
import '@shopify/polaris/build/esm/styles.css';
import {BrowserRouter} from 'react-router-dom';
import App from './App';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <AppProvider i18n={{}}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </AppProvider>,
);
