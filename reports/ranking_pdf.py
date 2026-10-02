"""A temporary, vector-text scorecard PDF with verified data and chart images."""
from __future__ import annotations
import io
import colorsys
import math
import numpy as np
from datetime import datetime, timezone
from html import escape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

NAVY='#14213D';BLUE='#1A4F8B';MUTED='#65758B';LINE='#DCE3EC'
PALETTE=['#1A4F8B','#487EA7','#286E66','#785A91','#A55767','#596773']
WIDTH,HEIGHT=792,612


def build_ranking_pdf(job,analytics,reference=None,horizon='200d'):
    from reports.pdf_report import _register_fonts
    FONT, BOLD, DISPLAY = _register_fonts()
    buffer=io.BytesIO();c=canvas.Canvas(buffer,pagesize=(WIDTH,HEIGHT));c.setTitle('GSWM - Technical Stock Scorecard');c.setAuthor('Gottfried & Somberg Wealth Management')
    rows=sorted(job['rows'],key=lambda r:(r['status']!='ready',-r.get('score',0),r['ticker']))
    ready=[r for r in rows if r['status']=='ready']; page=0
    paragraph=ParagraphStyle('body',fontName=FONT,fontSize=9,leading=13,textColor=HexColor(NAVY))
    def text(x,y,value,size=10,color=NAVY,font=FONT):
        c.setFillColor(HexColor(color));c.setFont(font,size);c.drawString(x,y,str(value))
    def para(value,x,y,width,size=9):
        style=ParagraphStyle('small',parent=paragraph,fontSize=size,leading=size*1.45)
        p=Paragraph(escape(value),style);_,h=p.wrap(width,500);p.drawOn(c,x,y-h);return h
    def start(title,subtitle):
        nonlocal page
        if page:c.showPage()
        page+=1;c.setFillColor(HexColor('#FFFFFF'));c.rect(0,0,WIDTH,HEIGHT,fill=1,stroke=0)
        text(44,576,'GOTTFRIED & SOMBERG WEALTH MANAGEMENT',9,BLUE,BOLD)
        text(44,543,title,25,NAVY,DISPLAY);text(44,523,subtitle,9,MUTED)
        c.setStrokeColor(HexColor(LINE));c.line(44,510,748,510);c.line(44,39,748,39)
        text(44,23,'Researcheus Maximus / Internal research / Technical setup assessment',8,MUTED)
        c.setFont(FONT,8);c.drawRightString(748,23,str(page))
    def chart_image(fig,x,y,w,h):
        FigureCanvasAgg(fig);image=io.BytesIO();fig.savefig(image,format='png',dpi=180,bbox_inches='tight',facecolor='white');image.seek(0)
        c.drawImage(ImageReader(image),x,y,width=w,height=h,preserveAspectRatio=True,anchor='c')
        fig.clear()
    def table(data,y=465):
        widths=[34,58,50,65,48,65,57,327];xs=[44]
        for width in widths[:-1]:xs.append(xs[-1]+width)
        headers=['Rank','Ticker','Score','12m return','RSI','63d vs SPY','ATR / price','Technical view']
        c.setFillColor(HexColor('#EAF1FA'));c.rect(44,y-10,704,24,fill=1,stroke=0)
        for x,h in zip(xs,headers):text(x+5,y,h,8,BLUE,BOLD)
        y-=35
        for rank,row in data:
            c.setStrokeColor(HexColor(LINE));c.line(44,y-12,748,y-12)
            if row['status']=='ready':
                values=[rank,row['ticker'],f"{row['score']:.1f}",f"{row['return_1y']:+.1f}%" if row.get('return_1y') is not None else '-',f"{row['rsi']:.1f}",f"{row['excess_63d']:+.1f} pp",f"{row['atr_pct']:.1f}%"]
            else:values=['-',row['ticker'],'N/A','-','-','-','-']
            for i,(x,v) in enumerate(zip(xs,values)):text(x+5,y,v,9,NAVY,BOLD if i in (1,2) else FONT)
            para(row['reason'],xs[-1]+5,y+7,320,8)
            y-=26
    generated=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC');dates=sorted(set(r['as_of'] for r in ready))
    date_label=dates[0] if len(dates)==1 else f'{dates[0]} to {dates[-1]}' if dates else 'Unavailable'
    start('Technical Stock Scorecard',f'1-3 month horizon / Model {job["version"]} / Data as of {date_label} / Generated {generated}')
    summary=[('Scored',str(len(ready))),('Average score',f'{sum(r["score"] for r in ready)/len(ready):.1f}' if ready else '-'),('Strong setups / 8+',str(sum(r['score']>=8 for r in ready))),('Unavailable',str(len(rows)-len(ready)))]
    for i,(label,value) in enumerate(summary):
        x=44+i*180;c.setFillColor(HexColor('#F7F9FC'));c.roundRect(x,422,164,68,7,fill=1,stroke=0);text(x+14,470,label,9,MUTED);text(x+14,439,value,23,NAVY,BOLD)
    text(44,397,'Highest-ranked setups',14,NAVY,DISPLAY);table(list(enumerate(ready[:10],1)),365)
    if analytics.get('available'):
        multi=[g for g in analytics['clusters'] if len(g['members'])>1]
        largest=max(multi,key=lambda g:len(g['members'])) if multi else None
        finding=f"Top {analytics['requested']} comparison: {len(analytics['tickers'])} usable stocks; mean pair correlation {analytics['average_correlation']:.2f}. "
        finding+=f"Largest group: {', '.join(largest['members'])}; average {largest['average_correlation']:.2f}." if largest else 'No group meets the 0.75 all-pairs threshold.'
        para(finding,44,78,704,8)
    else:para('Correlation graphs unavailable: '+analytics.get('reason','Insufficient data.'),44,78,704,8)
    if analytics.get('available'):
        mode='SPY exposure removed' if analytics['market_adjusted'] else 'Overall daily-return correlation'
        points=analytics['points'];groups=analytics['clusters']
        def color(p):
            if len(groups[p['cluster']]['members'])<=1:return '#8A98A9'
            group=p['cluster']
            if group<len(PALETTE):return PALETTE[group]
            rgb=colorsys.hls_to_rgb((round(group*137.508)%360)/360,.42,.42)
            return '#'+''.join(f'{round(channel*255):02x}' for channel in rgb)
        def label_points(fig,ax,coordinates):
            # Move labels only, preserving data coordinates and drawing leaders.
            FigureCanvasAgg(fig);fig.canvas.draw();renderer=fig.canvas.get_renderer();occupied=[]
            bounds=ax.get_window_extent(renderer)
            for p,x,y in coordinates[:20 if len(coordinates)<=20 else 10]:
                for distance in (12,24,36,48,60):
                    placed=False
                    for dx,dy in ((distance,distance),(distance,-distance),(-distance,distance),(-distance,-distance),(0,distance),(0,-distance)):
                        label=ax.annotate(p['ticker'],(x,y),xytext=(dx,dy),textcoords='offset points',ha='left' if dx>=0 else 'right',fontsize=8,color=NAVY,bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':1.5})
                        box=label.get_window_extent(renderer).expanded(1.08,1.15)
                        if bounds.contains(box.x0,box.y0) and bounds.contains(box.x1,box.y1) and not any(box.overlaps(other) for other in occupied):
                            occupied.append(box);ax.annotate('',(x,y),xytext=(dx,dy),textcoords='offset points',arrowprops={'arrowstyle':'-','color':color(p),'lw':.5});placed=True;break
                        label.remove()
                    if placed:break
        subtitle=f"Top {analytics['requested']} / {mode} / {analytics['sample_count']} returns / {analytics['start']} to {analytics['end']}"
        start('12-month return vs. technical score',subtitle)
        fig=Figure(figsize=(10,5));ax=fig.subplots();ax.spines[['top','right']].set_visible(False);ax.tick_params(colors=MUTED,labelsize=10);ax.grid(alpha=.15);ax.set_axisbelow(True)
        ax.set_xlabel('Trailing 12-month return (%)',fontsize=11,color=MUTED);ax.set_ylabel('Technical score / 10',fontsize=11,color=MUTED);ax.set_ylim(.7,10.5);ax.set_yticks(range(1,11));ax.axhspan(8,10,color='#EAF1FA',zorder=0)
        coordinates=[]
        for p in points:
            if p['return_1y'] is not None:
                ax.scatter(p['return_1y'],p['score'],s=40+p['score']*8,c=color(p),edgecolors='white',linewidth=1)
                coordinates.append((p,p['return_1y'],p['score']))
        ax.margins(x=.12);fig.tight_layout(pad=1.5);label_points(fig,ax,coordinates);chart_image(fig,44,124,704,366)
        para('Higher points have stronger technical scores; points further right gained more over the past year. The shaded band marks scores of 8-10. Color identifies correlation groups and point size reflects score. Similar scores or yearly gains alone do not establish correlation.',44,105,704,9)
        prior=horizon=='prior100d';return_key='return_prior100d' if prior else 'return_200d';y_label='Preceding 100-trading-day return' if prior else '200-trading-day return'
        start('Recent vs. preceding 100-day return' if prior else '100-day vs. 200-day return',subtitle)
        fig=Figure(figsize=(10,5));ax=fig.subplots();ax.spines[['top','right']].set_visible(False);ax.tick_params(colors=MUTED,labelsize=10);ax.grid(alpha=.15);ax.set_axisbelow(True)
        ax.set_xlabel('100-trading-day return (%)',fontsize=11,color=MUTED);ax.set_ylabel(y_label+' (%)',fontsize=11,color=MUTED)
        coordinates=[]
        for p in points:
            if p.get('return_100d') is not None and p.get(return_key) is not None:
                ax.scatter(p['return_100d'],p[return_key],s=40+p['score']*8,c=color(p),edgecolors='white',linewidth=1)
                coordinates.append((p,p['return_100d'],p[return_key]))
        if not coordinates:ax.text(.5,.5,'100- and 200-day returns unavailable. Run a fresh ranking.',transform=ax.transAxes,ha='center',color=MUTED)
        ax.margins(.12);fig.tight_layout(pad=1.5);label_points(fig,ax,coordinates);chart_image(fig,44,124,704,366)
        explanation=('The recent and preceding 100-day windows do not overlap. Upper-right gained in both periods; lower-right gained recently after losing previously. ' if prior else 'The 100-day window is part of the 200-day window. Shared data can strengthen the relationship between these axes. ')
        para(explanation+'Nearby stocks have similar cumulative performance. Colors use daily-return correlation, not point proximity. These patterns do not establish predictive signals. Returns stay actual when SPY exposure is removed from the correlation groups.',44,105,704,8)

        ref=reference if reference in analytics['tickers'] else analytics['tickers'][0];ref_index=analytics['tickers'].index(ref)
        start('Score vs. correlation to '+ref,subtitle)
        fig=Figure(figsize=(10,5));ax=fig.subplots();ax.spines[['top','right']].set_visible(False);ax.grid(alpha=.15);ax.set_axisbelow(True);ax.tick_params(colors=MUTED,labelsize=10)
        ax.set_xlabel('Daily-return correlation to '+ref,fontsize=11,color=MUTED);ax.set_ylabel('Technical score / 10',fontsize=11,color=MUTED);ax.set_xlim(-1.06,1.06);ax.set_ylim(.7,10.5);ax.set_xticks(np.arange(-1,1.01,.25));ax.set_yticks(range(1,11))
        from matplotlib.patches import Rectangle
        ax.add_patch(Rectangle((.75,8),.25,2,facecolor='#EAF1FA',zorder=0));ax.axvline(.75,color=BLUE,linestyle='--',linewidth=.8)
        coordinates=[];high=[]
        for i,p in enumerate(points):
            if p['ticker']==ref:continue
            value=analytics['matrix'][ref_index][i];ax.scatter(value,p['score'],s=40+p['score']*8,c=color(p),edgecolors='white',linewidth=1);coordinates.append((p,value,p['score']))
            if value>=.75 and p['score']>=8:high.append(p['ticker'])
        fig.tight_layout(pad=1.5);label_points(fig,ax,coordinates);chart_image(fig,44,124,704,366)
        finding=f"{len(high)} stocks meet score >=8 and correlation >=0.75 to {ref}: {', '.join(high) if high else 'none'}. "
        para(finding+'The reference stock is excluded. A strong link to the reference does not imply every highlighted peer is strongly correlated with every other peer. Group colors use the separate all-pairs rule. Correlation is historical and can change.',44,105,704,8)
        start('Reading the graphs',mode+' / Performance, current setup and daily co-movement')
        guides=[('01 / Return versus score','Higher points have stronger current technical setups; further right means larger past gains. The model already uses trend and momentum, so a relationship with past returns is partly mechanical. Predictive value requires historical scores formed without future information and tested against subsequent outcomes.'),('02 / Two return windows','The 100/200-day windows overlap. The preceding-100-day option instead compares two consecutive non-overlapping periods, exposing continuation and reversal patterns. Similar cumulative gains do not establish that stocks move together daily.'),('03 / Score versus correlation','Correlation is calculated from matched daily percentage returns. Upper-right means a strong setup and high correlation to the chosen stock. High reference correlation does not establish an all-pairs group. Removing market effect correlates residuals from separate stock-on-SPY regressions; actual cumulative returns stay unchanged.')]
        y=477
        for title,guide in guides:
            text(44,y,title,12,BLUE,BOLD);y-=22;y-=para(guide,44,y,704,10)+32
        grouped=[g for g in groups if len(g['members'])>1]
        if grouped:
            start('Correlated groups',f'{mode} / Every member pair must have correlation of at least 0.75')
            y=480
            for group in grouped:
                line=f"Group {group['id']+1}: {', '.join(group['members'])}. Average correlation {group['average_correlation']:.2f}; lowest pair {group['minimum_correlation']:.2f}."
                measure=Paragraph(escape(line),paragraph);_,height=measure.wrap(704,500)
                if y-height<65:
                    start('Correlated groups / continued',mode);y=480
                y-=para(line,44,y,704,10)+20
    ranked=[];rank=0
    for r in rows:
        if r['status']=='ready':rank+=1
        ranked.append((rank if r['status']=='ready' else '-',r))
    for offset in range(0,len(ranked),15):
        start('Full ranked watchlist',f'Stocks {offset+1}-{min(offset+15,len(ranked))} of {len(ranked)} / Highest score first / Equal scores ordered by ticker')
        table(ranked[offset:offset+15],470)
    y=0
    for r in ready:
        note=r.get('qualitative_summary',r['reason'])
        measure=Paragraph(escape(note),paragraph);_,height=measure.wrap(704,500)
        if y==0 or y-18-height-21<60:
            start('Position notes','Concise technical interpretation / Ranked order / All scored stocks')
            y=480
        text(44,y,f"{r['ticker']} / {r['score']:.1f} out of 10",11,BLUE,BOLD)
        y-=18
        y-=para(note,44,y,704,9)+21
    start('Methodology and data',f'Model {job["version"]} / Independent technical scores / 1-3 month horizon')
    y=480
    paragraphs=[
        'Scoring: trend 30%, momentum 20%, relative strength versus SPY 20%, entry/risk 20%, and directional volume 10%. Components range from 0 to 100; final score = 1 + 9 x weighted component total / 100. Scores are setup assessments, not return probabilities.',
        'Trend measures price relative to the 50/200-day moving averages and their slopes. Momentum combines RSI and MACD histogram direction. Relative strength uses 21/63-session excess returns versus SPY. Entry/risk considers extension above the 20-day average, support-based stop distance and ATR. Volume uses the last 20 sessions of directional volume.',
        'Correlations use up to 252 overlapping daily percentage returns, with a minimum of 126. No missing returns are filled with zero. Remove market effect fits each stock daily return on an intercept and SPY return, then correlates the residuals. Each correlation group requires every pair to meet 0.75. The 100-day and 200-day return windows overlap; their scatter shows similar performance rather than proving daily co-movement. The two performance plots use actual stock returns even when SPY exposure is removed from the correlation groups. The reference correlation plot uses the selected correlation mode.',
        'The 12-month chart uses 252 trading sessions and requires 253 prices. Yahoo adjusted history is preferred; verified Nasdaq fallback is unadjusted. Providers and price basis can vary. Stock/SPY scoring and each correlation comparison use a consistent price basis. Corporate actions can affect unadjusted indicators. Latest daily bars may be incomplete.',
        'Data quality: at least 220 valid recent daily sessions are required for scoring. Missing, stale, zero-volume or incompatible data receives no score. Stocks with a different price basis or insufficient return variation can be excluded from correlation analysis. Valuation, earnings-event risk and portfolio suitability are outside the model.',
    ]
    for p in paragraphs:y-=para(p,44,y,704,9)+17
    providers=sorted(set(r.get('data_provider','Yahoo Finance') for r in ready));text(44,y,'Sources used: '+', '.join(providers),9,BLUE,BOLD);y-=24
    para('Yahoo Finance: https://finance.yahoo.com/ | Nasdaq historical prices: https://www.nasdaq.com/market-activity | Per-stock source links, data providers and dates are included in the CSV export. Research is for internal review and does not place orders.',44,y,704,9)
    start('Chart research references','Methods and interpretation / Primary research and official documentation')
    references=[('NIST / Scatter Plot','Relationships, nonlinear patterns, outliers, and association versus causation. https://www.itl.nist.gov/div898/handbook/eda/section3/scatterp.htm'),('MathWorks / Plotting Financial Data','Stock-return series and scatter plots for examining relationships. https://www.mathworks.com/videos/plotting-financial-data-1603366137074.html'),('Plerou et al. / A Random Matrix Approach to Cross-Correlations in Financial Data','Research separates market-wide influence from correlated stock groups and noise. https://arxiv.org/abs/cond-mat/0108023'),('CFA Institute / Equity and Bond Correlations: Higher Than Assumed?','Return frequency and historical window affect estimated correlations. https://rpc.cfainstitute.org/blogs/enterprising-investor/2023/equity-and-bond-correlations-higher-than-assumed'),('CFA Institute / Backtesting and Simulation','Walk-forward validation, look-ahead bias and structural breaks. https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation')]
    y=480
    for title,description in references:
        text(44,y,title,10,BLUE,BOLD);y-=17;y-=para(description,44,y,704,8)+22
    c.save();return buffer.getvalue()
