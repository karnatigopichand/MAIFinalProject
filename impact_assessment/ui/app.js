const { useEffect, useRef, useState } = React;
const h = React.createElement;
const Fragment = React.Fragment;
const INITIAL_TICKET = 'DEMO-DELIVERY-1';
const INITIAL_SUMMARY = 'Pass delivery instructions from checkout to carrier and customer confirmation';
const INITIAL_DESCRIPTION = 'Customers can add delivery instructions at checkout. Forward them to the carrier and include them in the shipment confirmation.';
const INITIAL_CRITERIA = 'Instructions are optional and limited to 200 characters.\nInstructions are passed to the carrier when a shipment is created.\nThe shipment confirmation includes the instructions.';

async function api(path, body, token = '') {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers['Content-Type'] = 'application/json';
  let response;
  try {
    response = await fetch(path, body
      ? { method: 'POST', headers, body: JSON.stringify(body) }
      : { headers });
  } catch (_) {
    throw new Error(`Can't reach the demo API from ${location.origin}. Open the app at its server URL.`);
  }
  let data;
  try {
    data = await response.json();
  } catch (_) {
    throw new Error(`The demo API returned an unreadable response (HTTP ${response.status}).`);
  }
  if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  return data;
}

const niceName = value => String(value || '').replace(/^commerce-/, '').replace(/-/g, ' ');
const readable = value => String(value || '').replaceAll('_', ' ');

function Icon({ children, className = '' }) {
  return h('span', { className: `icon ${className}`.trim(), 'aria-hidden': 'true' }, children);
}

function Brand() {
  return h('a', { className: 'brand', href: '/', 'aria-label': 'Impact Atlas home' },
    h('span', { className: 'brand-icon', 'aria-hidden': 'true' }, 'IA'),
    h('span', null, 'Impact Atlas', h('small', null, 'CHANGE INTELLIGENCE')));
}

function App() {
  const [tab, setTab] = useState('assessment');
  const [accessToken, setAccessToken] = useState(() => sessionStorage.getItem('impactAtlasToken') || '');
  const [config, setConfig] = useState(null);
  const [services, setServices] = useState([]);
  const [serviceSummary, setServiceSummary] = useState('Checking services…');
  const [toast, setToast] = useState('');
  const [authRequired, setAuthRequired] = useState(false);
  const authDialog = useRef(null);
  const toastTimer = useRef(null);

  const notify = message => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(''), 3400);
  };

  useEffect(() => {
    api('/api/config').then(data => {
      setConfig(data);
      setAuthRequired(Boolean(data.auth_required));
    }).catch(() => setConfig({ jira_configured: false }));
  }, []);

  useEffect(() => {
    if (authRequired && !accessToken && authDialog.current && !authDialog.current.open) {
      authDialog.current.showModal();
    } else if ((!authRequired || accessToken) && authDialog.current?.open) {
      authDialog.current.close();
    }
  }, [authRequired, accessToken]);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const data = await api('/api/status', null, accessToken);
        if (!active) return;
        const entries = [
          ...data.services.map(service => ({
            name: niceName(service.name),
            status: ['ok', 'up'].includes(service.status) ? 'ok' : 'down',
          })),
          { name: 'ActiveMQ broker', status: data.broker === 'reachable' ? 'ok' : 'down' },
        ];
        setServices(entries);
        setServiceSummary(`${entries.filter(item => item.status === 'ok').length} / ${entries.length} dependencies available`);
      } catch (_) {
        if (active) setServiceSummary('Service status unavailable');
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, [accessToken]);

  const connect = event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const token = String(data.get('token') || '');
    sessionStorage.setItem('impactAtlasToken', token);
    setAccessToken(token);
    notify('Demo session connected.');
  };

  return h(Fragment, null,
    h('header', { className: 'topbar' },
      h(Brand),
      h('div', { className: 'top-right' },
        h('span', { className: 'live-dot', 'aria-hidden': 'true' }),
        h('span', null, 'LOCAL DEMO'),
        h('span', { className: 'pill' }, 'EVIDENCE SNAPSHOT'))),
    h('main', null,
      h('section', { className: 'intro' },
        h('div', { className: 'intro-copy' },
          h('div', { className: 'eyebrow' }, 'AUTONOMOUS IMPACT ASSESSMENT'),
          h('h1', null, 'See the change', h('br'), h('em', null, 'before it ships.')),
          h('p', null, 'Trace a Jira request across services, contracts, events, and technical debt. Every finding links back to repository evidence.')),
        h('div', { className: 'intro-art', 'aria-hidden': 'true' },
          h('div', { className: 'orbit orbit-a' }), h('div', { className: 'orbit orbit-b' }),
          h('div', { className: 'core' }, '↗'),
          h('span', { className: 'node n1' }, 'API'), h('span', { className: 'node n2' }, 'EVENT'),
          h('span', { className: 'node n3' }, 'TEST'), h('span', { className: 'node n4' }, 'DEBT'))),
      h('section', { className: 'status-wrap', 'aria-labelledby': 'environment-title' },
        h('div', { className: 'section-kicker' },
          h('h2', { id: 'environment-title' }, 'Demo environment'),
          h('span', { role: 'status', 'aria-live': 'polite' }, serviceSummary)),
        h('div', { className: 'service-grid' }, services.map(service =>
          h('div', { className: `service ${service.status}`, key: service.name },
            h('span', { className: 'service-dot', 'aria-hidden': 'true' }),
            h('span', { className: 'service-name' }, service.name),
            h('span', { className: 'service-state' }, service.status === 'ok' ? 'Available' : 'Unavailable'))))),
      h('nav', { className: 'tabs', 'aria-label': 'Demo views' },
        h('button', { type: 'button', className: `tab ${tab === 'assessment' ? 'active' : ''}`,
          'aria-current': tab === 'assessment' ? 'page' : undefined, onClick: () => setTab('assessment') },
          h('span', { className: 'tab-index' }, '01'), 'Impact assessment'),
        h('button', { type: 'button', className: `tab ${tab === 'commerce' ? 'active' : ''}`,
          'aria-current': tab === 'commerce' ? 'page' : undefined, onClick: () => setTab('commerce') },
          h('span', { className: 'tab-index' }, '02'), 'Commerce journey'),
        h('span', { className: 'tab-note' }, 'TWO WAYS TO EXPLORE THE SYSTEM')),
      h('section', { className: `panel ${tab === 'assessment' ? 'active' : ''}`, id: 'assessment-panel',
        'aria-labelledby': 'assessment-title', hidden: tab !== 'assessment' },
        h('div', { className: 'panel-heading' },
          h('div', null,
            h('div', { className: 'eyebrow' }, 'JIRA → EVIDENCE → DECISION'),
            h('h2', { id: 'assessment-title' }, 'Investigate a change'),
            h('p', null, 'Map a requirement’s blast radius, compare related debt, and get cited engineering recommendations.')),
          h('span', { className: 'tag' }, 'READ-ONLY ANALYSIS')),
        h(AssessmentPanel, { token: accessToken, jiraConfigured: config?.jira_configured, notify }),
      ),
      h('section', { className: `panel ${tab === 'commerce' ? 'active' : ''}`, id: 'commerce-panel',
        'aria-labelledby': 'commerce-title', hidden: tab !== 'commerce' },
        h('div', { className: 'panel-heading' },
          h('div', null,
            h('div', { className: 'eyebrow' }, 'CHECKOUT → PAYMENT → SHIPPING'),
            h('h2', { id: 'commerce-title' }, 'Follow a commerce journey'),
            h('p', null, 'Submit a synthetic checkout and watch asynchronous order, shipment, and notification events arrive.')),
          h('span', { className: 'tag synthetic' }, 'SYNTHETIC PROVIDERS')),
        h(CommercePanel, { token: accessToken, notify }),
      ),
      h('footer', null,
        h('span', null, 'IMPACT ATLAS · LOCAL PROTOTYPE'),
        h('span', null, 'Assess changes with evidence. Keep the decision human.'))),
    h('dialog', { className: 'auth-dialog', ref: authDialog, onCancel: event => {
      if (authRequired && !accessToken) event.preventDefault();
    } },
      h('form', { onSubmit: connect },
        h('div', { className: 'eyebrow' }, 'DEMO ACCESS'),
        h('h2', null, 'Connect to Impact Atlas'),
        h('p', null, 'This deployment requires its demo access token.'),
        h('label', { htmlFor: 'access-token' }, 'Access token'),
        h('input', { id: 'access-token', name: 'token', type: 'password', autoComplete: 'current-password', required: true }),
        h('button', { className: 'button primary', type: 'submit' }, 'Continue', h(Icon, null, '↗')))),
    h('div', { className: `toast ${toast ? 'show' : ''}`, role: 'status', 'aria-live': 'polite' }, toast));
}

function JiraKeyInput({ value, onChange, onChoose, token, disabled }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [note, setNote] = useState('Search sample stories or enter your own issue ID.');
  const sequence = useRef(0);
  const inputId = 'jira-issue-key';
  const listId = 'jira-suggestions';

  useEffect(() => {
    const query = value.trim();
    const current = ++sequence.current;
    if (query.length < 2) {
      setSuggestions([]);
      setOpen(false);
      setNote('Search sample stories or enter your own issue ID.');
      return undefined;
    }
    setNote('Searching sample Jira stories…');
    const timer = window.setTimeout(async () => {
      try {
        const result = await api('/api/jira-search', { query }, token);
        if (current !== sequence.current) return;
        const issues = result.issues || [];
        setSuggestions(issues);
        setOpen(issues.length > 0);
        setActiveIndex(-1);
        setNote(issues.length
          ? 'Choose a suggestion to load it, or keep typing a manual issue ID.'
          : 'No matching samples. Enter a manual issue ID and provide its details.');
      } catch (_) {
        if (current === sequence.current) {
          setSuggestions([]);
          setOpen(false);
          setNote('Suggestions unavailable. You can still enter a Jira key or manual ID.');
        }
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [value, token]);

  const choose = issue => {
    setOpen(false);
    setSuggestions([]);
    onChoose(issue);
  };

  const handleKeyDown = event => {
    if (event.key === 'ArrowDown' && suggestions.length) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex(index => (index + 1) % suggestions.length);
    } else if (event.key === 'ArrowUp' && suggestions.length) {
      event.preventDefault();
      setActiveIndex(index => (index <= 0 ? suggestions.length - 1 : index - 1));
    } else if (event.key === 'Enter' && open && activeIndex >= 0) {
      event.preventDefault();
      choose(suggestions[activeIndex]);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };

  return h('div', { className: 'jira-key-control' },
    h('label', { htmlFor: inputId }, 'Jira issue key or manual ID'),
    h('div', { className: 'typeahead' },
      h('input', {
        id: inputId, value, onChange: event => { onChange(event.target.value); setOpen(true); },
        onFocus: () => { if (suggestions.length) setOpen(true); }, onBlur: () => window.setTimeout(() => setOpen(false), 120),
        onKeyDown: handleKeyDown, autoComplete: 'off', maxLength: 80, required: true, disabled,
        placeholder: 'Search Jira or type a manual ID', role: 'combobox', 'aria-autocomplete': 'list',
        'aria-expanded': open && suggestions.length > 0, 'aria-controls': listId,
        'aria-activedescendant': activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined,
      }),
      open && suggestions.length > 0 && h('div', { className: 'suggestion-menu', id: listId, role: 'listbox' },
        suggestions.map((issue, index) => h('div', {
          id: `${listId}-${index}`, key: issue.key, role: 'option',
          'aria-selected': activeIndex === index, className: `suggestion ${activeIndex === index ? 'active' : ''}`,
          onMouseDown: event => event.preventDefault(), onClick: () => choose(issue),
        }, h('strong', null, issue.key), h('span', null, issue.summary))))),
    h('small', { className: 'field-hint', role: 'status', 'aria-live': 'polite' }, note));
}

function AssessmentPanel({ token, jiraConfigured, notify }) {
  const [ticketId, setTicketId] = useState(INITIAL_TICKET);
  const [summary, setSummary] = useState(INITIAL_SUMMARY);
  const [description, setDescription] = useState(INITIAL_DESCRIPTION);
  const [criteria, setCriteria] = useState(INITIAL_CRITERIA);
  const [loadingJira, setLoadingJira] = useState(false);
  const [running, setRunning] = useState(false);
  const [assessment, setAssessment] = useState(null);
  const [error, setError] = useState('');
  const lastLoadedKey = useRef('');

  const changeTicket = value => {
    setTicketId(value);
    if (value.trim() !== lastLoadedKey.current) {
      setSummary('');
      setDescription('');
      setCriteria('');
      setAssessment(null);
    }
  };

  const loadIssue = async issueKey => {
    const key = String(issueKey || ticketId).trim();
    if (!key) return;
    setLoadingJira(true);
    setError('');
    try {
      const ticket = await api('/api/jira-issue', { issue_key: key }, token);
      lastLoadedKey.current = ticket.ticket_id || key;
      setTicketId(lastLoadedKey.current);
      setSummary(ticket.summary || '');
      setDescription(ticket.description || '');
      setCriteria((ticket.acceptance_criteria || []).join('\n'));
      notify(`Loaded ${lastLoadedKey.current}. Review it, then run the assessment.`);
    } catch (issueError) {
      setError(issueError.message);
      notify(issueError.message);
    } finally {
      setLoadingJira(false);
    }
  };

  const chooseIssue = issue => {
    changeTicket(issue.key);
    loadIssue(issue.key);
  };

  const loadAmbiguousExample = () => {
    lastLoadedKey.current = '';
    setTicketId('DEMO-SHIPPING-AMBIGUOUS');
    setSummary('Offer expedited shipping and notify the recipient');
    setDescription('Allow customers to expedite shipping for an order and notify the recipient. The request does not define delivery timing, eligibility, or pricing.');
    setCriteria('');
    setAssessment(null);
    setError('');
    notify('Ambiguous example loaded. Run the assessment to see focused questions.');
  };

  const submit = async event => {
    event.preventDefault();
    setRunning(true);
    setAssessment(null);
    setError('');
    try {
      const result = await api('/api/assess', {
        ticket_id: ticketId.trim(), summary, description,
        acceptance_criteria: criteria.split('\n').map(line => line.trim()).filter(Boolean),
      }, token);
      setAssessment(result);
    } catch (runError) {
      setError(runError.message);
    } finally {
      setRunning(false);
    }
  };

  return h('div', { className: 'assessment-layout' },
    h('form', { className: 'card form-card', onSubmit: submit },
      h(JiraKeyInput, { value: ticketId, onChange: changeTicket, onChoose: chooseIssue, token, disabled: running }),
      h('div', { className: 'jira-fetch' },
        h('button', { className: 'button secondary', id: 'load-jira-issue', type: 'button',
          disabled: loadingJira || running, onClick: () => loadIssue() },
          loadingJira ? 'Loading Jira issue…' : 'Load issue from Jira', h(Icon, null, '↓')),
        h('small', { className: 'field-hint' }, jiraConfigured
          ? 'Jira is connected on the app server.'
          : 'Jira credentials are not configured on the app server.')),
      h('label', { htmlFor: 'ticket-summary' }, 'Summary'),
      h('input', { id: 'ticket-summary', value: summary, onChange: event => setSummary(event.target.value),
        maxLength: 300, required: true, disabled: running, placeholder: 'Summarize the requested change' }),
      h('label', { htmlFor: 'ticket-description' }, 'Description'),
      h('textarea', { id: 'ticket-description', value: description, onChange: event => setDescription(event.target.value),
        rows: 5, maxLength: 8000, disabled: running, placeholder: 'Describe the requirement and context' }),
      h('label', { htmlFor: 'ticket-criteria' }, 'Acceptance criteria', h('span', { className: 'field-hint inline-hint' }, 'One per line')),
      h('textarea', { id: 'ticket-criteria', value: criteria, onChange: event => setCriteria(event.target.value),
        rows: 4, maxLength: 8000, disabled: running, placeholder: 'Add a verifiable criterion on each line' }),
      error && h('p', { className: 'form-error', role: 'alert' }, error),
      h('button', { className: 'button primary', type: 'submit', disabled: running || !summary.trim() },
        running ? 'Investigating evidence…' : 'Run impact assessment', h(Icon, null, '↗')),
      h('p', { className: 'form-foot' }, 'Uses repository evidence and cited standards · Read-only recommendations'),
      h('button', { className: 'text-button', type: 'button', onClick: loadAmbiguousExample },
        'Load ambiguous expedited-shipping example', h(Icon, null, '↗'))),
    h('div', { className: 'result-area', id: 'assessment-result', 'aria-live': 'polite' },
      running
        ? h('div', { className: 'empty-state loading-state' }, h('div', { className: 'loading-orbit', 'aria-hidden': 'true' }),
          h('h3', null, 'Following the change through the codebase'),
          h('p', null, 'Searching repository evidence and trusted engineering standards…'))
        : error && !assessment
          ? h('div', { className: 'empty-state error-state' }, h('h3', null, 'Assessment could not run'), h('p', null, error))
          : assessment
            ? h(AssessmentResponse, { assessment })
            : h('div', { className: 'empty-state' },
              h('div', { className: 'empty-symbol', 'aria-hidden': 'true' }, '⌁'),
              h('h3', null, 'Your impact map starts here'),
              h('p', null, 'Run an assessment to see affected services, dependency paths, risks, debt overlap, and source evidence.'),
              h('div', { className: 'empty-chips' }, ['API contracts', 'Event flows', 'Technical debt'].map(label => h('span', { key: label }, label))))));
}

function AssessmentResponse({ assessment }) {
  const [fullOpen, setFullOpen] = useState(false);
  const impacts = assessment.impacts || [];
  const risks = assessment.risks || [];
  const evidence = assessment.evidence || [];
  const questions = assessment.questions || [];
  const citations = new Map(evidence.map(item => [item.evidence_id, item]));
  const citationNodes = ids => (ids || []).map((id, index) => {
    const item = citations.get(id);
    const label = item ? `${item.repository}/${item.path}:${item.line_start}-${item.line_end}` : id;
    return h('code', { key: `${id}-${index}` }, label);
  }).flatMap((node, index, all) => index < all.length - 1 ? [node, ' · '] : [node]);

  const classification = assessment.classification;
  const recommendations = assessment.code_recommendations || [];
  const recommendationTrace = (assessment.trace || []).find(item => item.agent === 'code-recommendation-engine');
  const recommendationParams = recommendationTrace?.parameters || {};
  const noRecommendationsText = recommendationParams.source_count
    ? `Web search found ${recommendationParams.source_count} approved sources, but no recommendation passed repository-evidence and citation checks. See the investigation trace for details.`
    : 'Web search found no approved source pages for this run. The evidence-backed impact assessment is still available.';

  const impactContent = impacts.length
    ? impacts.map((item, index) => h('article', { className: 'finding', key: `${item.finding_id || item.repository}-${index}` },
      h('span', { className: 'badge' }, readable(item.classification)),
      h('h5', null, `${item.repository} · ${item.component}`),
      h('p', null, `${item.claim} ${item.business_relevance}`),
      h('div', { className: 'citation-list' }, citationNodes(item.evidence_ids))))
    : h('p', { className: 'muted' }, 'No direct impacts returned.');

  const riskContent = risks.length
    ? risks.map((item, index) => h('article', { className: 'risk-item', key: `${item.failure_mode}-${index}` },
      h('span', { className: `badge ${/high|critical/i.test(item.severity) ? 'warn' : ''}` }, `${item.severity} risk`),
      h('h5', null, item.failure_mode),
      h('p', null, `${item.business_consequence} · Validate: ${(item.recommended_validation || []).join('; ')}`),
      h('div', { className: 'citation-list' }, citationNodes(item.evidence_ids))))
    : h('p', { className: 'muted' }, 'No specific risks were verified from retrieved evidence.');

  const debtItems = assessment.debt_assessments || [];
  const recommendationContent = recommendations.length
    ? recommendations.map((item, index) => h('article', { className: 'recommendation-item', key: `${item.repository}-${index}` },
      h('h5', null, `${item.repository} · ${item.title}`),
      h('p', null, item.recommendation),
      h('p', { className: 'muted' }, `Why it fits: ${item.rationale}`),
      h('p', null, 'Local evidence: ', citationNodes(item.evidence_ids)),
      item.code_example && h('pre', null, h('code', null, item.code_example)),
      h('div', { className: 'recommendation-sources' }, (item.sources || []).map(source =>
        h('a', { key: source.url, href: source.url, target: '_blank', rel: 'noopener noreferrer' }, `${source.title} ↗`)))))
    : h('p', { className: 'muted' }, recommendationsMessage(assessment.code_recommendation_status, noRecommendationsText));

  const traceItems = assessment.trace || [];
  const paths = assessment.dependency_paths || [];
  const report = () => {
    const blob = new Blob([assessment.report_markdown || ''], { type: 'text/markdown' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${assessment.context.ticket_id}-impact-report.md`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return h('div', { className: 'assessment-result' },
    h('div', { className: 'result-head' },
      h('div', null, h('h3', null, 'Assessment response'),
        h('small', null, `${assessment.context.ticket_id} · snapshot ${assessment.context.snapshot_id}`)),
      h('div', { className: 'result-actions' },
        assessment.langfuse_trace_url
          ? h('a', { className: 'trace-link', href: assessment.langfuse_trace_url, target: '_blank', rel: 'noopener noreferrer' }, 'Open Langfuse trace ↗')
          : h('span', { className: 'trace-state' }, `Langfuse ${readable(assessment.langfuse_trace_status || 'not configured')} · local trace below`),
        h('button', { className: 'download', type: 'button', onClick: report }, '↓ Report'))),
    h('div', { className: 'summary-card' },
      h('span', { className: 'eyebrow' }, readable(assessment.status).toUpperCase()),
      h('p', null, assessment.summary)),
    classification
      ? h('div', { className: 'classification-peek', 'aria-label': 'Jira impact classification summary' },
        classificationChip('Scope', readable(classification.impact_scope?.label || 'unclear')),
        classificationChip('Change', readable(classification.change_kind?.label || 'mixed or unclear')),
        classificationChip('Clarity', classification.clarity?.label || 'unknown'),
        classification.review_recommended && h('span', { className: 'classification-chip review-chip' }, 'Review suggested'))
      : h('div', { className: 'classification-peek' }, h('span', { className: 'classification-chip' }, `Classification ${readable(assessment.classification_status || 'not configured')}`)),
    h('a', { className: 'full-response-link', href: '#full-response', 'aria-controls': 'full-response',
      'aria-expanded': fullOpen, onClick: event => { event.preventDefault(); setFullOpen(open => !open); } },
      `${fullOpen ? 'Hide' : 'View'} full response · ${impacts.length} impacts · ${questions.length} questions · ${evidence.length} evidence items ${fullOpen ? '↑' : '↓'}`),
    h('details', { className: 'assessment-response', id: 'full-response', open: fullOpen },
      h('summary', { className: 'visually-hidden' }, 'Full assessment response'),
      h('div', { className: 'assessment-response-body' },
        h(CollapsibleRow, { title: 'Assessment metrics', open: true },
          h('div', { className: 'metric-row' },
            metric(impacts.length, 'Impact findings'), metric(risks.length, 'Risks'), metric(evidence.length, 'Evidence items'))),
        h(CollapsibleRow, { title: 'Jira impact classification', open: true, className: 'classification-row' },
          h('div', { className: 'classification-detail' },
            h('span', null, h('b', null, classification?.provider || 'Classifier')),
            h('span', null, `Scope confidence ${classification?.impact_scope?.confidence ?? 'n/a'}`),
            h('span', null, `Change confidence ${classification?.change_kind?.confidence ?? 'n/a'}`),
            h('span', null, `Clarification probability ${classification?.requires_clarification_probability ?? 'n/a'}`),
            h('span', null, classification?.review_recommended ? 'Human review suggested' : 'No review flag'))),
        h(CollapsibleRow, { title: 'Clarifications · Business risks · Service impact', open: true, className: 'three-column-row' },
          h(ResultCard, { title: 'Clarifications needed' }, questions.length
            ? h('ul', null, questions.map((question, index) => h('li', { key: index }, question)))
            : h('p', { className: 'muted' }, 'No clarification questions for this assessment.')),
          h(ResultCard, { title: 'Business risks & validation' }, riskContent),
          h(ResultCard, { title: 'Service and component impact' }, impactContent)),
        h(CollapsibleRow, { title: 'Code recommendations · Technical debt · Dependency paths', open: true, className: 'three-column-row' },
          h(ResultCard, { title: 'Code recommendations · industry sources' }, recommendationContent,
            recommendations.length > 0 && h('p', { className: 'muted' }, 'Recommendations are advisory; validate against project evidence and team conventions.')),
          h(ResultCard, { title: 'Technical debt overlap' }, debtItems.length
            ? debtItems.map((item, index) => h('article', { className: 'debt-item', key: `${item.debt_id}-${index}` },
              h('span', { className: `badge ${item.disposition === 'consider' ? 'warn' : ''}` }, readable(item.disposition)),
              h('h5', null, `${item.repository} · ${item.title}`),
              h('p', null, `${item.reason} · ${item.total_hours == null ? 'effort unknown' : `${item.total_hours}h incl. testing`}`),
              h('p', null, `Shared tests: ${(item.shared_tests || []).join(', ') || 'none identified'}`)))
            : h('p', { className: 'muted' }, 'No related debt items.')),
          h(ResultCard, { title: 'Dependency paths' }, paths.length
            ? h('ul', null, paths.map((path, index) => h('li', { key: index }, typeof path === 'string' ? path : JSON.stringify(path))))
            : h('p', { className: 'muted' }, 'No dependency paths were confirmed.'))),
        h(CollapsibleRow, { title: `Evidence used · ${evidence.length} items`, open: true, className: 'full-row' },
          h(ResultCard, { title: `Evidence used (${evidence.length})` }, evidence.length
            ? evidence.slice(0, 16).map((item, index) => h('article', { className: 'evidence-item', key: `${item.evidence_id}-${index}` },
              h('h5', null, `${item.repository} · ${item.section || item.document_type}`),
              h('p', null, item.excerpt),
              h('code', null, `${item.path}:${item.line_start}-${item.line_end} · ${item.commit}`)))
            : h('p', { className: 'muted' }, 'No evidence attached.'))),
        h(CollapsibleRow, { title: `Show investigation trace · ${traceItems.length} events`, className: 'full-row trace-row' },
          traceItems.length
            ? h('ol', { className: 'trace-list' }, traceItems.map((item, index) => h('li', { key: `${item.agent}-${index}` },
              h('b', null, `${item.agent} · ${item.name}`), ` · ${item.outcome}`,
              item.duration_ms != null && ` · ${Math.round(item.duration_ms)}ms`,
              h('details', { className: 'trace-event' }, h('summary', null, 'Inspect event'),
                h('pre', null, JSON.stringify({ type: item.event_type, parameters: item.parameters,
                  evidence_ids: item.evidence_ids, error: item.error }, null, 2))))))
            : h('p', { className: 'muted' }, 'No trace events are available.')))));
}

function recommendationsMessage(status, emptyMessage) {
  const messages = {
    not_configured: 'Set OPENAI_API_KEY on the app server to enable cited web recommendations.',
    disabled: 'Web recommendations are disabled.',
    unavailable: 'Web search was unavailable; the evidence-backed impact assessment is still available.',
    skipped_no_verified_impacts: 'No verified impact was available to scope a code recommendation.',
    no_cited_recommendations: emptyMessage,
  };
  return messages[status] || 'No web recommendations were returned.';
}

function classificationChip(label, value) {
  return h('span', { className: 'classification-chip', key: label },
    h('small', null, label), value);
}

function metric(value, label) {
  return h('div', { className: 'metric', key: label }, h('b', null, value), h('span', null, label));
}

function ResultCard({ title, children, className = '' }) {
  return h('section', { className: `result-block ${className}`.trim() }, h('h4', null, title), children);
}

function CollapsibleRow({ title, children, className = '', open = false }) {
  return h('details', { className: `response-row ${className}`.trim(), open: open || undefined },
    h('summary', null, title), h('div', { className: 'response-row-content' }, children));
}

function CommercePanel({ token, notify }) {
  const [form, setForm] = useState({ sku: 'book', quantity: '1', total_cents: '2500', payment_token: 'demo-token', delivery_address: '10 Main St, New York, NY' });
  const [sending, setSending] = useState(false);
  const [orderId, setOrderId] = useState('');
  const [orderData, setOrderData] = useState(null);
  const [journeyTitle, setJourneyTitle] = useState('Waiting for checkout');
  const [selectedEvent, setSelectedEvent] = useState('checkout');
  const [error, setError] = useState('');
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    if (!orderId || attempts >= 12 || orderData?.shipment) return undefined;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const state = await api(`/api/order/${encodeURIComponent(orderId)}`, null, token);
        if (!active) return;
        setOrderData(current => ({ ...(current || {}), ...state }));
        setAttempts(value => value + 1);
        if (state.shipment || attempts >= 11) {
          setJourneyTitle(state.shipment ? 'Shipment and events received' : 'Order accepted · awaiting shipment');
        }
      } catch (_) {
        if (active) setAttempts(value => value + 1);
      }
    }, 1200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [orderId, orderData, attempts, token]);

  const setField = (name, value) => setForm(current => ({ ...current, [name]: value }));
  const submit = async event => {
    event.preventDefault();
    setSending(true);
    setError('');
    setOrderId('');
    setOrderData(null);
    setAttempts(0);
    setJourneyTitle('Order in progress');
    try {
      const response = await api('/api/commerce-order', {
        sku: form.sku,
        quantity: Number(form.quantity),
        total_cents: Number(form.total_cents),
        payment_token: form.payment_token,
        delivery_address: form.delivery_address,
      }, token);
      setOrderId(response.order_id);
      setOrderData(response);
      setJourneyTitle('Order accepted · waiting for shipment');
      notify('Checkout accepted. Following its events…');
    } catch (submitError) {
      setError(submitError.message);
      setJourneyTitle('Checkout failed');
    } finally {
      setSending(false);
    }
  };

  const stepStates = {
    checkout: Boolean(orderId),
    payment: orderData?.checkout?.status === 'confirmed',
    shipment: Boolean(orderData?.shipment),
    notification: Boolean(orderData?.order_notification || orderData?.shipment_notification),
  };
  const eventSteps = [
    ['checkout', 'Checkout accepted', 'Cart sent to order service'],
    ['payment', 'Payment authorized', 'Mock payment provider'],
    ['shipment', 'Shipment created', 'Carrier tracking assigned'],
    ['notification', 'Customer notified', 'Order and shipment messages'],
  ];
  const eventDetails = {
    checkout: {
      title: 'Checkout accepted', status: stepStates.checkout ? 'Accepted' : 'Waiting',
      message: stepStates.checkout ? 'The checkout request was accepted by the commerce service.' : 'Place a demo order to create a checkout event.',
      data: orderData?.checkout || (orderId ? { order_id: orderId } : null),
    },
    payment: {
      title: 'Payment authorization', status: stepStates.payment ? 'Authorized' : 'Waiting',
      message: stepStates.payment
        ? 'The order was confirmed after payment authorization. The demo API does not return the provider authorization ID.'
        : 'Payment authorization follows inventory reservation when checkout is submitted.',
      data: stepStates.payment ? { order_id: orderId, status: 'authorized', amount_cents: Number(form.total_cents), currency: 'USD' } : null,
    },
    shipment: {
      title: 'Shipment created', status: stepStates.shipment ? 'Created' : 'Waiting',
      message: stepStates.shipment ? 'The carrier assigned tracking details to this order.' : 'Shipment details will appear after the order event is consumed.',
      data: orderData?.shipment || null,
    },
    notification: {
      title: 'Customer notifications', status: stepStates.notification ? 'Sent' : 'Waiting',
      message: stepStates.notification ? 'Notification service stored the order and/or shipment message.' : 'Order and shipment notifications arrive asynchronously.',
      data: stepStates.notification ? {
        order_notification: orderData?.order_notification || null,
        shipment_notification: orderData?.shipment_notification || null,
      } : null,
    },
  };

  return h('div', { className: 'commerce-layout' },
    h('form', { className: 'card form-card', onSubmit: submit },
      h('div', { className: 'two-col' },
        h(Field, { label: 'SKU', id: 'commerce-sku' }, h('input', { id: 'commerce-sku', value: form.sku, required: true,
          onChange: event => setField('sku', event.target.value) })),
        h(Field, { label: 'Quantity', id: 'commerce-quantity' }, h('input', { id: 'commerce-quantity', type: 'number', value: form.quantity,
          min: 1, max: 100, required: true, onChange: event => setField('quantity', event.target.value) }))),
      h('div', { className: 'two-col' },
        h(Field, { label: 'Total · cents', id: 'commerce-total' }, h('input', { id: 'commerce-total', type: 'number', value: form.total_cents,
          min: 1, required: true, onChange: event => setField('total_cents', event.target.value) })),
        h(Field, { label: 'Payment token', id: 'commerce-token' }, h('select', { id: 'commerce-token', value: form.payment_token,
          onChange: event => setField('payment_token', event.target.value) },
          h('option', { value: 'demo-token' }, 'demo-token'), h('option', { value: 'demo-decline' }, 'demo-decline')))),
      h(Field, { label: 'Delivery address', id: 'commerce-address' }, h('input', { id: 'commerce-address', value: form.delivery_address, required: true,
        onChange: event => setField('delivery_address', event.target.value) })),
      error && h('p', { className: 'form-error', role: 'alert' }, error),
      h('button', { className: 'button primary', type: 'submit', disabled: sending },
        sending ? 'Sending checkout…' : orderId ? 'Place another order' : 'Place demo order', h(Icon, null, '↗')),
      h('p', { className: 'form-foot' }, 'No real payment is taken and no real carrier is contacted.')),
    h('section', { className: 'journey card', 'aria-labelledby': 'journey-title' },
      h('div', { className: 'journey-head' },
        h('div', null, h('div', { className: 'eyebrow' }, 'EVENT TIMELINE'), h('h3', { id: 'journey-title', role: 'status', 'aria-live': 'polite' }, journeyTitle)),
        h('span', { className: 'pulse', 'aria-hidden': 'true' })),
      h('div', { className: 'steps', role: 'group', 'aria-label': 'Select an event to inspect' }, eventSteps.map(([key, title, detail], index) => h('button', {
        type: 'button', className: `step ${stepStates[key] ? 'complete' : ''} ${selectedEvent === key ? 'selected' : ''}`,
        key, 'aria-pressed': selectedEvent === key, onClick: () => setSelectedEvent(key),
        'aria-label': `${title}: ${stepStates[key] ? 'Complete' : 'Pending'}`,
      },
        h('span', { className: 'step-icon', 'aria-hidden': 'true' }, `0${index + 1}`),
        h('div', null, h('b', null, title), h('small', null, detail)),
        h('span', { className: 'step-state' }, stepStates[key] ? 'Complete' : 'Pending')))),
      h(EventDetailCard, eventDetails[selectedEvent])));
}

function EventDetailCard({ title, status, message, data }) {
  return h('section', { className: 'event-detail-card', 'aria-live': 'polite', 'aria-labelledby': 'selected-event-title' },
    h('div', { className: 'event-detail-head' },
      h('div', null, h('span', { className: 'eyebrow' }, 'SELECTED EVENT'), h('h4', { id: 'selected-event-title' }, title)),
      h('span', { className: `event-status ${status === 'Waiting' ? 'pending' : 'complete'}` }, status)),
    h('p', null, message),
    data
      ? h('pre', { className: 'event-payload' }, JSON.stringify(data, null, 2))
      : h('p', { className: 'event-empty' }, 'No event payload is available yet.'));
}

function Field({ label, id, children }) {
  return h('div', { className: 'field-group' }, h('label', { htmlFor: id }, label), children);
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(h(App));
