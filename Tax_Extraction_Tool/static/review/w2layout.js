/* Drake Tax 2025 · Screen W2 — exact layout (940 × 657), measured from the Drake screenshot.
   Ported from templates/w2_mapping.html. `map` turns a layout box into a catalog field key;
   boxes without a catalog field are drawn read-only (Drake fields we do not fill from the PDF). */
window.DRAKE_LAYOUTS = window.DRAKE_LAYOUTS || {};
(function(){
  const BOXES = [
    ['ts','cb',39,79,43],['f','in',108,79,19],['stt','cb',306,79,44],
    ['ein','in',133,122,90],['ername','in',133,141,314],['ernc','in',133,160,314],['erst','in',133,178,314],['ercity','in',133,196,197],
    ['erstate','cb',133,230,54],['erzip','in',209,230,90],['erprov','dis',133,266,198],['ercountry','cbd',352,266,53],['erpostal','ro',427,266,80],
    ['eefirst','in',133,324,135],['eelast','in',321,324,180],['eest','in',133,342,314],['eecity','in',133,360,197],
    ['eestate','cb',133,395,55],['eezip','in',209,395,90],['eeprov','dis',133,426,198],['eecountry','cbd',352,426,53],['eepostal','ro',427,426,80],
    ['b1','in',550,118,91],['b2','in',715,118,90],['b3','in',550,156,91],['b4','in',715,156,90],
    ['b5','in',550,195,91],['b6','in',715,195,90],['b7','in',550,234,91],['b8','in',715,234,90],
    ['b9','ro',550,273,142],['b10','in',715,274,90],['b11','in',550,323,91],
    ['stat','ck',551,352],['ret','ck',551,366],['sick','ck',551,380],
    ['altered','ck',12,572],['corrected','ck',371,572],['noupd','ck',487,572],['agent','ck',716,568],
    ['itin','in',663,614,99],
  ];
  ['a','b','c','d'].forEach((r,i)=>{ const y=322+i*18; BOXES.push(['c12'+r,'cb',715,y,55],['a12'+r,'in',776,y,90],['y12'+r,'in',874,y,37]); });
  [403,421,439,458].forEach((y,i)=>BOXES.push(['o14a'+(i+1),'in',622,y,73],['o14b'+(i+1),'in',715,y,90]));
  [496,515,533,551].forEach((y,i)=>{ const n=i+1; BOXES.push(['st'+n,'cb',12,y,55],['sid'+n,'in',83,y,144],['sw'+n,'in',253,y,90],['stx'+n,'in',370,y,90],['lw'+n,'in',485,y,91],['ltx'+n,'in',599,y,90],['loc'+n,'cb',715,y,110]); });

  const TEXT = [
    ['Form W-2 - Wage and Tax Statement',16,55,'h1'],
    ['TS',16,81,'ts'],['F',90,81,''],['Special tax treatment',152,82,''],
    ['EIN',23,127,'dots',126],['Name',23,145,'dots',126],['Name cont',23,164,'dots',126],['Street',23,182,'dots',126],['City',23,200,'dots',126],
    ['U.S.ONLY',23,218,'b'],['State',131,215,''],['ZIP',207,215,''],
    ['Foreign ONLY',23,252,'b'],['Province/state',131,252,''],['Country',351,252,''],['Postal code',423,252,''],
    ['Name:',23,329,''],['First',71,328,'dots',122],['Last',269,329,'dots',311],['Street',23,347,'dots',122],['City',23,365,'dots',122],
    ['U.S. ONLY',23,380,'b'],['State',131,380,''],['ZIP',207,380,''],
    ['Foreign ONLY',23,413,'b'],['Province/state',131,413,''],['Country',350,414,''],['Postal code',423,413,''],
    ['=',125,327,'red'],['=',314,327,'red'],['=',125,345,'red'],['=',125,363,'red'],['=',125,398,'red'],['=',201,398,'red'],['=',125,429,'red'],['=',343,429,'red'],['=',419,429,'red'],
    ['1',525,104,'b'],['Wages, tips',550,104,''],['2',692,104,'b'],['Federal tax w/h',713,104,''],
    ['3',525,141,'b'],['Soc. Sec. wages',549,141,''],['4',691,141,'b'],['Soc. Sec. w/h',713,141,''],
    ['5',525,180,'b'],['Medicare wages',549,180,''],['6',691,180,'b'],['Medicare tax w/h',713,181,''],
    ['7',525,219,'b'],['Soc. Sec. tips',549,220,''],['8',691,219,'b'],['Allocated tips',713,220,''],
    ['9',524,259,'b'],['10',692,259,'b'],['Dep. care benefit',713,259,''],['Form 2441',826,274,'lnk'],['Form 8880',826,294,'lnk'],
    ['11',526,308,'b'],['Nonqualified  plan',549,308,''],['12',692,308,'b'],['Code',713,308,''],['Amount',774,308,''],['Year',873,308,''],
    ['13',526,351,'b'],['Statutory employee',565,351,''],['Retirement plan',565,366,''],['Sick pay',565,379,''],
    ['14',526,401,'b'],['Other',549,401,''],['SEHI',551,416,'lnk'],['8889',551,431,'lnk'],['QSEHRA',824,401,'lnk'],
    ['Video: Entering Multiple-State W2s',702,30,'lnk'],
    ['15',11,482,'b'],['ST',35,482,''],["Employer's State ID Number",82,482,''],['16',251,482,'b'],['State Wages',270,482,''],
    ['17',368,482,'b'],['State Tax',385,482,''],['18',484,482,'b'],['Local Wages',502,482,''],['19',601,482,'b'],['Local Tax',621,482,''],
    ['20',713,482,'b'],['Locality',735,482,''],
    ['W-2 altered or handwritten (nonstandard)',28,573,''],['Corrected W-2',386,573,''],['Do not update to 2026',511,573,''],['Agent for employer',730,570,''],
    ['If either spouse has an ITIN on screen 1, enter the TIN from Form W-2',16,618,'dots',656],
    ['IN',723,66,'lnk'],['NJ',753,66,'lnk'],['ND',784,66,'lnk'],['NY',813,66,'lnk'],['PA',843,66,'lnk'],
  ];
  const CHROME =
    `<div class="tab sel" style="left:0;width:31px">W-2</div><div class="tab" style="left:30px;width:112px">Additional Entries</div><div class="tab" style="left:141px;width:36px">Ohio</div>` +
    `<div class="tabline"></div><div class="tbtn" style="left:201px;width:88px">Import W2</div><div class="bottomline" style="top:645px"></div>` +
    `<div class="frame" style="left:12px;top:110px;width:500px;height:179px"></div><div class="lg" style="left:21px;top:103px">Employer Information</div>` +
    `<div class="frame" style="left:12px;top:310px;width:500px;height:143px"></div><div class="lg" style="left:21px;top:303px">Employee Name and Address (if different from screen 1)</div>` +
    `<div class="frame" style="left:9px;top:607px;width:770px;height:29px"></div>` +
    `<div class="frame" style="left:695px;top:56px;width:178px;height:27px"></div><div class="lg" style="left:704px;top:49px">State Information</div>`;
  const MAP = {
    ts:'ts', ein:'employer_ein', ername:'employer_name', ernc:'employer_name2', erst:'employer_street', ercity:'employer_city',
    erstate:'employer_state', erzip:'employer_zip', eest:'employee_street', eecity:'employee_city', eestate:'employee_state', eezip:'employee_zip',
    b1:'box1', b2:'box2', b3:'box3', b4:'box4', b5:'box5', b6:'box6', b7:'box7', b8:'box8', b10:'box10', b11:'box11',
    stat:'box13_statutory', ret:'box13_retirement', sick:'box13_sick',
    c12a:'box12a_code', a12a:'box12a_amount', c12b:'box12b_code', a12b:'box12b_amount', c12c:'box12c_code', a12c:'box12c_amount', c12d:'box12d_code', a12d:'box12d_amount',
    o14a1:'box14', st1:'state1', sid1:'state1_id', sw1:'state1_wages', stx1:'state1_tax', lw1:'local1_wages', ltx1:'local1_tax', loc1:'locality1',
  };
  window.DRAKE_LAYOUTS['W2'] = {width:940, height:657, boxes:BOXES, text:TEXT, chrome:CHROME, map:MAP,
    blue:new Set(['ein','ername','erst','ercity','erstate','erzip']),
    notes:{eest:'Fill only if different from Screen 1', eecity:'Fill only if different from Screen 1', eestate:'Fill only if different from Screen 1', eezip:'Fill only if different from Screen 1'}};
})();
