<template>
  <div>
    <!-- 模式标签页 -->
    <div class="page-card">
      <el-tabs v-model="mode">
        <el-tab-pane label="单股回测" name="single" />
        <el-tab-pane label="组合回测" name="portfolio" />
        <el-tab-pane label="策略对比" name="compare" />
        <el-tab-pane label="参数优化" name="optimize" />
        <el-tab-pane label="AI 预测" name="ai_simple" />
        <el-tab-pane label="AI 回测" name="ai_backtest" />
      </el-tabs>

      <!-- ====== 单股回测表单 ====== -->
      <el-form v-if="mode === 'single'" :model="form" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="股票代码"><el-input v-model="form.code" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="策略">
            <el-select v-model="form.strategy">
              <el-option label="SMA 双均线" value="sma" />
              <el-option label="动量策略" value="momentum" />
              <el-option label="买入持有" value="buy_hold" />
              <el-option label="均线多头排列" value="ma_alignment" />
            </el-select>
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="K线周期">
            <el-select v-model="form.period">
              <el-option label="日线" :value="240" />
              <el-option label="30分钟" :value="30" />
              <el-option label="60分钟" :value="60" />
            </el-select>
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="初始资金">
            <el-input-number v-model="form.cash" :min="10000" :step="10000" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="起始日期">
            <el-date-picker v-model="form.start" type="date" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="结束日期">
            <el-date-picker v-model="form.end" type="date" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="复权方式">
            <el-radio-group v-model="form.adjust">
              <el-radio-button value="qfq">前复权</el-radio-button>
              <el-radio-button value="hfq">后复权</el-radio-button>
            </el-radio-group>
          </el-form-item></el-col>
          <template v-if="form.strategy === 'sma'">
            <el-col :span="8"><el-form-item label="快线"><el-input-number v-model="form.fast" :min="2" :max="60" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="慢线"><el-input-number v-model="form.slow" :min="5" :max="250" /></el-form-item></el-col>
          </template>
          <template v-if="form.strategy === 'momentum'">
            <el-col :span="8"><el-form-item label="回看期"><el-input-number v-model="form.lookback" :min="5" :max="120" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="动量阈值"><el-input-number v-model="form.thresh" :min="0.01" :max="0.5" :step="0.01" :precision="2" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="止损"><el-input-number v-model="form.stop_loss" :min="0.01" :max="0.5" :step="0.01" :precision="2" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="止盈"><el-input-number v-model="form.take_profit" :min="0.05" :max="1.0" :step="0.05" :precision="2" /></el-form-item></el-col>
          </template>
          <template v-if="form.strategy === 'ma_alignment'">
            <el-col :span="8"><el-form-item label="快线周期"><el-input-number v-model="form.fast" :min="2" :max="60" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="中线周期"><el-input-number v-model="form.mid" :min="3" :max="120" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="慢线周期"><el-input-number v-model="form.slow" :min="5" :max="250" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="量能均线周期"><el-input-number v-model="form.vol_period" :min="5" :max="120" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="放量倍数"><el-input-number v-model="form.vol_ratio" :min="1.0" :max="5.0" :step="0.1" :precision="1" /></el-form-item></el-col>
          </template>
        </el-row>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runSingle">
            <el-icon><VideoPlay /></el-icon>开始回测
          </el-button>
        </el-form-item>
      </el-form>

      <!-- ====== 组合回测表单 ====== -->
      <el-form v-else-if="mode === 'portfolio'" :model="pfForm" label-width="100px">
        <el-form-item label="股票代码">
          <el-input v-model="pfForm.codes" placeholder="逗号分隔" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="策略">
            <el-select v-model="pfForm.strategy">
              <el-option label="SMA 双均线" value="sma" />
              <el-option label="动量策略" value="momentum" />
            </el-select>
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="起始日期"><el-date-picker v-model="pfForm.start" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="结束日期"><el-date-picker v-model="pfForm.end" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="初始资金"><el-input-number v-model="pfForm.cash" :min="10000" :step="10000" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="快线"><el-input-number v-model="pfForm.fast" :min="2" :max="60" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="慢线"><el-input-number v-model="pfForm.slow" :min="5" :max="250" /></el-form-item></el-col>
        </el-row>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runPortfolio">
            <el-icon><VideoPlay /></el-icon>开始组合回测
          </el-button>
        </el-form-item>
      </el-form>

      <!-- ====== 策略对比 ====== -->
      <el-form v-else-if="mode === 'compare'" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="股票代码"><el-input v-model="compareForm.code" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="初始资金"><el-input-number v-model="compareForm.cash" :min="10000" :step="10000" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="起始日期"><el-date-picker v-model="compareForm.start" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="结束日期"><el-date-picker v-model="compareForm.end" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="复权方式">
            <el-radio-group v-model="compareForm.adjust">
              <el-radio-button value="qfq">前复权</el-radio-button>
              <el-radio-button value="hfq">后复权</el-radio-button>
            </el-radio-group>
          </el-form-item></el-col>
        </el-row>
        <el-form-item label="选择策略">
          <el-checkbox-group v-model="compareForm.strategies" class="strategy-checkboxes">
            <el-checkbox
              v-for="s in availableStrategies" :key="s.id"
              :value="s.id" :label="s.id"
            >
              <span class="cb-name">{{ s.name }}</span>
              <span class="cb-desc">{{ s.description?.slice(0, 30) }}{{ (s.description?.length || 0) > 30 ? '...' : '' }}</span>
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runCompare">
            <el-icon><VideoPlay /></el-icon>开始对比 ({{ compareForm.strategies.length }} 个策略)
          </el-button>
        </el-form-item>
      </el-form>

      <!-- ====== 参数优化 ====== -->
      <el-form v-else-if="mode === 'optimize'" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="股票代码"><el-input v-model="optForm.code" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="策略">
            <el-select v-model="optForm.strategy" @change="onOptStrategyChange">
              <el-option
                v-for="s in optimizableStrategies" :key="s.id"
                :label="s.name" :value="s.id"
              />
            </el-select>
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="初始资金"><el-input-number v-model="optForm.cash" :min="10000" :step="10000" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="起始日期"><el-date-picker v-model="optForm.start" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="结束日期"><el-date-picker v-model="optForm.end" type="date" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="复权方式">
            <el-radio-group v-model="optForm.adjust">
              <el-radio-button value="qfq">前复权</el-radio-button>
              <el-radio-button value="hfq">后复权</el-radio-button>
            </el-radio-group>
          </el-form-item></el-col>
        </el-row>
        <el-form-item label="优化参数">
          <div class="params-editor">
            <div v-if="optParams.length === 0" style="color: var(--text-placeholder); font-size: var(--text-sm);">
              请先选择一个策略（需要策略有数字参数）
            </div>
            <div v-for="p in optParams" :key="p.key" class="param-opt-row">
              <span class="param-label">{{ p.label }}</span>
              <el-input-number v-model="p.min" :min="p.origMin" :max="p.max" size="small" style="width:100px;" />
              <span style="color: var(--text-placeholder);">~</span>
              <el-input-number v-model="p.max" :min="p.min" :max="p.origMax" size="small" style="width:100px;" />
              <span style="color: var(--text-placeholder); font-size: var(--text-xs);">
                步长
                <el-input-number v-model="p.step" :min="0.1" :max="p.max - p.min" size="small" :step="1" :precision="0" style="width:80px;" />
              </span>
              <span style="color: var(--text-secondary); font-size: var(--text-xs);">
                {{ countCombinations(p) }} 个值
              </span>
            </div>
          </div>
        </el-form-item>
        <el-form-item v-if="optParams.length > 0">
          预计运行 <strong>{{ totalCombinations }}</strong> 次回测
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runOptimize" :disabled="totalCombinations > 500">
            <el-icon><VideoPlay /></el-icon>开始优化 ({{ totalCombinations > 500 ? '参数组合过多,请缩小范围' : '最多500次' }})
          </el-button>
          <span v-if="optProgress.total > 0" style="margin-left: 12px; color: var(--text-secondary);">
            进度: {{ optProgress.done }} / {{ optProgress.total }}
          </span>
          <el-progress
            v-if="optProgress.total > 0"
            :percentage="Math.round(optProgress.done / optProgress.total * 100)"
            style="width: 200px; margin-left: 12px;"
          />
        </el-form-item>
      </el-form>

      <!-- ====== AI 预测 ====== -->
      <el-form v-else-if="mode === 'ai_simple'" :model="aiForm" label-width="120px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="股票代码">
              <el-input v-model="aiForm.code" placeholder="如 000001" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="复权方式">
              <el-radio-group v-model="aiForm.adjust">
                <el-radio-button value="qfq">前复权</el-radio-button>
                <el-radio-button value="hfq">后复权</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="模型">
              <el-select v-model="aiForm.model" style="width:160px;">
                <el-option v-for="m in kronosStatus.models" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="历史窗口(天)"><el-input-number v-model="aiForm.lookback" :min="30" :max="512" :step="30" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="预测长度(天)"><el-input-number v-model="aiForm.pred_len" :min="1" :max="120" :step="5" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="温度"><el-input-number v-model="aiForm.temperature" :min="0.1" :max="2.0" :step="0.1" :precision="1" /></el-form-item></el-col>
        </el-row>
        <el-form-item>
          <el-button v-if="!kronosStatus.loaded" type="warning" :loading="kronosLoading" @click="kronosLoadModel">
            <el-icon><Download /></el-icon>加载模型
          </el-button>
          <el-button v-else type="danger" plain :loading="kronosLoading" @click="kronosUnloadModel">
            <el-icon><Unlock /></el-icon>卸载模型
          </el-button>
          <el-button type="primary" :loading="predicting" :disabled="!kronosStatus.loaded" @click="runPredictSimple">
            <el-icon><MagicStick /></el-icon>开始预测
          </el-button>
          <el-button @click="loadKronosStatus">
            <el-icon><Refresh /></el-icon>刷新状态
          </el-button>
        </el-form-item>
        <el-alert v-if="!kronosStatus.available" type="warning" :closable="false" show-icon>
          <template #title>Kronos 不可用</template>
          <div>{{ kronosStatus.error || '请检查 torch / vendor/Kronos 是否就绪' }}</div>
        </el-alert>
      </el-form>

      <!-- ====== AI 回测 ====== -->
      <el-form v-else-if="mode === 'ai_backtest'" :model="aiForm" label-width="120px">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px;">
          <template #title>回测说明</template>
          使用「训练截止日」之前的数据预测之后 M 天,与数据库中的真实 K 线对比,计算准确率。
        </el-alert>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="股票代码"><el-input v-model="aiForm.code" placeholder="如 000001" /></el-form-item></el-col>
          <el-col :span="8">
            <el-form-item label="复权方式">
              <el-radio-group v-model="aiForm.adjust">
                <el-radio-button value="qfq">前复权</el-radio-button>
                <el-radio-button value="hfq">后复权</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="8"><el-form-item label="模型">
            <el-select v-model="aiForm.model" style="width:160px;">
              <el-option v-for="m in kronosStatus.models" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="训练截止日"><el-date-picker v-model="aiForm.train_end" type="date" value-format="YYYY-MM-DD" placeholder="选择历史截止日" style="width:100%;" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="历史窗口(天)"><el-input-number v-model="aiForm.lookback" :min="30" :max="512" :step="30" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="预测长度(天)"><el-input-number v-model="aiForm.pred_len" :min="1" :max="120" :step="5" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="温度"><el-input-number v-model="aiForm.temperature" :min="0.1" :max="2.0" :step="0.1" :precision="1" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="top_p"><el-input-number v-model="aiForm.top_p" :min="0.0" :max="1.0" :step="0.05" :precision="2" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="采样次数"><el-input-number v-model="aiForm.sample_count" :min="1" :max="10" /></el-form-item></el-col>
        </el-row>
        <el-form-item>
          <el-button v-if="!kronosStatus.loaded" type="warning" :loading="kronosLoading" @click="kronosLoadModel">
            <el-icon><Download /></el-icon>加载模型
          </el-button>
          <el-button v-else type="danger" plain :loading="kronosLoading" @click="kronosUnloadModel">
            <el-icon><Unlock /></el-icon>卸载模型
          </el-button>
          <el-button type="primary" :loading="predicting" :disabled="!kronosStatus.loaded" @click="runPredictBacktest">
            <el-icon><VideoPlay /></el-icon>运行回测
          </el-button>
          <el-button @click="useRecentPreset" plain>
            <el-icon><RefreshRight /></el-icon>推荐:用最近 1 个月数据
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- ====== 回测结果 ====== -->
    <div class="page-card" v-if="result">
      <h3 class="page-title">回测结果</h3>
      <div class="metric-grid">
        <div class="metric-item">
          <div class="label">期末资金</div>
          <div class="value">{{ fmtMoney(result.final_value) }}</div>
        </div>
        <div class="metric-item" :class="result.pnl >= 0 ? 'green' : 'red'">
          <div class="label">总盈亏</div>
          <div class="value">{{ fmtMoney(result.pnl) }} ({{ (result.pnl_pct || 0).toFixed(2) }}%)</div>
        </div>
        <div class="metric-item" :class="(result.annual_return || 0) >= 0 ? 'green' : 'red'">
          <div class="label">年化收益</div>
          <div class="value">{{ (result.annual_return || 0).toFixed(2) }}%</div>
        </div>
        <div class="metric-item orange">
          <div class="label">最大回撤</div>
          <div class="value">{{ (result.max_drawdown || 0).toFixed(2) }}%</div>
        </div>
        <div class="metric-item">
          <div class="label">夏普比率</div>
          <div class="value">{{ (result.sharpe || 0).toFixed(3) }}</div>
        </div>
        <div class="metric-item">
          <div class="label">SQN</div>
          <div class="value">{{ (result.sqn || 0).toFixed(2) }}</div>
        </div>
      </div>
    </div>

    <!-- ====== 组合汇总 ====== -->
    <div class="page-card" v-if="portfolioItems.length">
      <h3 class="page-title">组合汇总 ({{ portfolioItems.length }} 只)</h3>
      <el-table :data="portfolioItems">
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="收益率" align="right">
          <template #default="{ row }">
            <span :class="(row.pnl_pct || 0) >= 0 ? 'up' : 'down'">
              {{ (row.pnl_pct || 0).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="年化%" align="right">
          <template #default="{ row }">{{ (row.annual_return || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="最大回撤%" align="right">
          <template #default="{ row }">{{ (row.max_drawdown || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="夏普" align="right">
          <template #default="{ row }">{{ (row.sharpe || 0).toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="期末资金" align="right">
          <template #default="{ row }">{{ fmtMoney(row.final_value) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ====== 策略对比结果 ====== -->
    <div class="page-card" v-if="compareResults.length">
      <h3 class="page-title">策略对比结果 ({{ compareResults.length }} 个策略)</h3>
      <el-table :data="compareResults" :row-class-name="compareRowClass">
        <el-table-column prop="strategyName" label="策略" min-width="140" />
        <el-table-column label="收益率" align="right" sortable>
          <template #default="{ row }">
            <span :class="(row.pnl_pct || 0) >= 0 ? 'up' : 'down'">
              {{ (row.pnl_pct || 0).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="年化%" align="right" sortable>
          <template #default="{ row }">{{ (row.annual_return || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="最大回撤%" align="right" sortable>
          <template #default="{ row }">{{ (row.max_drawdown || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="夏普" align="right" sortable>
          <template #default="{ row }">{{ (row.sharpe || 0).toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="SQN" align="right">
          <template #default="{ row }">{{ (row.sqn || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="期末资金" align="right">
          <template #default="{ row }">{{ fmtMoney(row.final_value) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ====== 参数优化结果 ====== -->
    <div class="page-card" v-if="optBestResult">
      <h3 class="page-title">最优参数</h3>
      <div class="metric-grid">
        <div v-for="(v, k) in optBestParams" :key="k" class="metric-item green">
          <div class="label">{{ k }}</div>
          <div class="value">{{ v }}</div>
        </div>
      </div>
      <div class="metric-grid" style="margin-top: 12px;">
        <div class="metric-item">
          <div class="label">最优收益率</div>
          <div class="value">{{ (optBestResult.pnl_pct || 0).toFixed(2) }}%</div>
        </div>
        <div class="metric-item">
          <div class="label">最优年化</div>
          <div class="value">{{ (optBestResult.annual_return || 0).toFixed(2) }}%</div>
        </div>
        <div class="metric-item">
          <div class="label">最优夏普</div>
          <div class="value">{{ (optBestResult.sharpe || 0).toFixed(3) }}</div>
        </div>
      </div>
    </div>

    <div class="page-card" v-if="optAllResults.length > 0">
      <h3 class="page-title">优化结果排名 (Top 20)</h3>
      <el-table :data="optAllResults.slice(0, 20)" max-height="400">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column label="参数" min-width="200">
          <template #default="{ row }">
            <span v-for="(v, k) in row.params" :key="k" style="margin-right: 8px;">
              <el-tag size="small" effect="plain">{{ k }}: {{ v }}</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="收益率" align="right" width="100">
          <template #default="{ row }">
            <span :class="(row.pnl_pct || 0) >= 0 ? 'up' : 'down'">
              {{ (row.pnl_pct || 0).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="年化%" align="right" width="80">
          <template #default="{ row }">{{ (row.annual_return || 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="夏普" align="right" width="80">
          <template #default="{ row }">{{ (row.sharpe || 0).toFixed(3) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ====== AI 回测准确率 ====== -->
    <div class="page-card" v-if="aiResult && aiResult.mode === 'backtest' && aiResult.metrics">
      <h3 class="page-title">AI 回测准确率</h3>
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="metric-item" :class="(aiResult.metrics.direction_accuracy || 0) >= 55 ? 'green' : (aiResult.metrics.direction_accuracy || 0) >= 45 ? 'orange' : 'red'">
            <div class="label">方向正确率</div>
            <div class="value">{{ aiResult.metrics.direction_accuracy }}%</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="label">MAE</div>
            <div class="value">{{ aiResult.metrics.mae.toFixed(3) }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item" :class="(aiResult.metrics.mape || 0) <= 3 ? 'green' : (aiResult.metrics.mape || 0) <= 6 ? 'orange' : 'red'">
            <div class="label">MAPE</div>
            <div class="value">{{ aiResult.metrics.mape.toFixed(2) }}%</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="label">对比天数</div>
            <div class="value">{{ aiResult.metrics.compared_days }}</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- ====== AI 预测图表 ====== -->
    <div class="page-card" v-if="aiResult">
      <h3 class="page-title">
        {{ aiResult.mode === 'backtest' ? 'AI 回测结果(预测 vs 实际)' : 'AI 预测结果' }}
        <el-tag v-if="aiResult" style="margin-left:12px;">
          {{ aiResult.code }} · {{ aiResult.mode === 'backtest' ? '回测 ' + aiResult.pred_len + ' 天' : '预测 ' + aiResult.pred_len + ' 天' }}
        </el-tag>
      </h3>
      <div ref="aiChartRef" class="kline-chart" style="height:480px;"></div>
    </div>

    <!-- ====== AI 回测数据明细 ====== -->
    <div class="page-card" v-if="aiResult && aiResult.mode === 'backtest' && aiBacktestRows.length">
      <h3 class="page-title">AI 回测数据明细(预测 vs 实际)</h3>
      <el-table :data="aiBacktestRows" max-height="400">
        <el-table-column prop="trade_date" label="日期" width="120" fixed />
        <el-table-column label="预测收盘" align="right">
          <template #default="{ row }">{{ Number(row.close_pred).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="实际收盘" align="right">
          <template #default="{ row }">{{ Number(row.close_actual).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="误差%" align="right">
          <template #default="{ row }">
            <span :class="Math.abs(row.error_pct) < 3 ? 'up' : 'down'">
              {{ row.error_pct > 0 ? '+' : '' }}{{ row.error_pct.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="方向命中" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.hit" type="success" size="small">✓</el-tag>
            <el-tag v-else type="danger" size="small">✗</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ====== AI 预测明细 ====== -->
    <div class="page-card" v-if="aiResult && aiResult.mode === 'simple' && aiResult.prediction && aiResult.prediction.length">
      <h3 class="page-title">AI 预测明细</h3>
      <el-table :data="aiResult.prediction" max-height="380">
        <el-table-column prop="trade_date" label="日期" width="120" fixed />
        <el-table-column label="开盘" align="right">
          <template #default="{ row }">{{ Number(row.open).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="最高" align="right">
          <template #default="{ row }">{{ Number(row.high).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="最低" align="right">
          <template #default="{ row }">{{ Number(row.low).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="收盘" align="right">
          <template #default="{ row }">{{ Number(row.close).toFixed(2) }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { backtestApi, kronosApi } from '@/api/modules'
import { BUILTIN_STRATEGIES, loadStrategies, strategyToBacktestParams } from '@/utils/strategy'
import { chartThemeColors } from '@/utils/chartTheme'

const route = useRoute()

// 模式
const mode = ref('single')
const running = ref(false)
const result = ref(null)
const portfolioItems = ref([])

// 所有可用策略
const allStrategies = computed(() => [...BUILTIN_STRATEGIES, ...loadStrategies()])
const availableStrategies = computed(() => allStrategies.value)
const optimizableStrategies = computed(() =>
  allStrategies.value.filter(s => s.params.length > 0 && s.type !== 'buy_hold')
)

// 单股回测
const form = reactive({
  code: '000001', strategy: 'sma', cash: 100000, period: 240,
  start: '2022-01-01', end: '2024-12-31', adjust: 'qfq',
  fast: 5, slow: 20, lookback: 20, thresh: 0.05, stop_loss: 0.08, take_profit: 0.20,
  mid: 10, vol_period: 20, vol_ratio: 1.2,
})

// 组合回测
const pfForm = reactive({
  codes: '000001,600000,600519', strategy: 'sma', cash: 100000,
  start: '2022-01-01', end: '2024-12-31', adjust: 'qfq',
  fast: 5, slow: 20, lookback: 20,
})

// 策略对比
const compareForm = reactive({
  code: '000001', cash: 100000, start: '2022-01-01', end: '2024-12-31', adjust: 'qfq',
  strategies: [],
})
const compareResults = ref([])

// 参数优化
const optForm = reactive({
  code: '000001', strategy: '', cash: 100000,
  start: '2022-01-01', end: '2024-12-31', adjust: 'qfq',
})
const optParams = ref([])
const optBestResult = ref(null)
const optBestParams = ref({})
const optAllResults = ref([])
const optProgress = reactive({ total: 0, done: 0 })

const totalCombinations = computed(() => {
  if (optParams.value.length === 0) return 0
  let total = 1
  for (const p of optParams.value) {
    const count = countCombinations(p)
    if (count === 0) return 0
    total *= count
  }
  return total
})

function countCombinations(p) {
  if (p.max <= p.min || !p.step || p.step <= 0) return 0
  return Math.floor((p.max - p.min) / p.step) + 1
}

function fmtMoney(v) {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function compareRowClass({ row }) {
  if (row._isBest) return 'best-row'
  return ''
}

// 获取策略信息
function getStrategy(id) {
  return allStrategies.value.find(s => s.id === id)
}

// 2026-08-04: 统一把策略(内置/自定义)转成后端回测参数,
// 不再硬映射 custom→sma(修复"假自定义"缺陷)
function strategyToPayload(s) {
  const payload = strategyToBacktestParams(s)
  return payload
}

// 单股回测
async function runSingle() {
  running.value = true
  result.value = null; portfolioItems.value = []; compareResults.value = []; optAllResults.value = []
  try {
    const r = await backtestApi.single({ ...form })
    result.value = r.data
    ElMessage.success('回测完成')
  } catch (e) { ElMessage.error(e.message) }
  finally { running.value = false }
}

// 组合回测
async function runPortfolio() {
  running.value = true
  result.value = null; portfolioItems.value = []; compareResults.value = []; optAllResults.value = []
  try {
    const r = await backtestApi.portfolio({ ...pfForm })
    portfolioItems.value = r.data.items || []
    ElMessage.success(`完成 ${portfolioItems.value.length} 只股票回测`)
  } catch (e) { ElMessage.error(e.message) }
  finally { running.value = false }
}

// 策略对比
async function runCompare() {
  if (compareForm.strategies.length === 0) {
    return ElMessage.warning('请至少选择一个策略')
  }
  running.value = true
  result.value = null; compareResults.value = []; portfolioItems.value = []; optAllResults.value = []
  try {
    const promises = compareForm.strategies.map(async (sid) => {
      const s = getStrategy(sid)
      if (!s) return null
      const payload = { ...compareForm }
      delete payload.strategies

      // 2026-08-04: 统一走 strategyToPayload(修复 custom 类型 400 / 假自定义)
      Object.assign(payload, strategyToPayload(s))

      const r = await backtestApi.single(payload)
      return { strategyName: s.name, strategyId: s.id, ...(r.data || r) }
    })

    const results = (await Promise.all(promises)).filter(Boolean)
    // 标记最佳（按收益率）
    if (results.length > 0) {
      let best = results[0]
      for (const r of results) {
        if ((r.pnl_pct || 0) > (best.pnl_pct || 0)) best = r
      }
      best._isBest = true
    }
    compareResults.value = results
    ElMessage.success(`完成 ${results.length} 个策略对比`)
  } catch (e) { ElMessage.error(e.message) }
  finally { running.value = false }
}

// 参数优化 - 选择策略时更新优化参数
function onOptStrategyChange(sid) {
  const s = getStrategy(sid)
  if (!s) { optParams.value = []; return }
  optParams.value = (s.params || [])
    .filter(p => p.type === 'number')
    .map(p => ({
      key: p.key,
      label: p.label || p.key,
      min: p.min ?? 1,
      max: p.max ?? 100,
      step: Math.max(1, Math.floor(((p.max ?? 100) - (p.min ?? 1)) / 5)),
      origMin: p.min ?? 1,
      origMax: p.max ?? 100,
    }))
}

// 运行参数优化 (网格搜索)
async function runOptimize() {
  const s = getStrategy(optForm.strategy)
  if (!s) return ElMessage.warning('请选择策略')
  if (totalCombinations.value === 0) return ElMessage.warning('无有效参数组合')
  if (totalCombinations.value > 500) return ElMessage.warning('参数组合超过 500 个,请缩小参数范围')

  running.value = true
  optBestResult.value = null; optAllResults.value = []; optBestParams.value = {}
  result.value = null; compareResults.value = []; portfolioItems.value = []
  optProgress.total = totalCombinations.value
  optProgress.done = 0

  try {
    // 生成所有参数组合
    const combos = generateCombinations()
    const results = []

    for (const combo of combos) {
      const payload = { ...optForm }
      delete payload.strategy

      // 2026-08-04: 统一走 strategyToPayload(修复 custom 类型 400)
      Object.assign(payload, strategyToPayload(s))
      // 覆盖为网格值
      for (const p of optParams.value) {
        payload[p.key] = combo[p.key]
      }

      try {
        const r = await backtestApi.single(payload)
        const data = r.data || r
        results.push({ params: { ...combo }, ...data })
      } catch {
        // 某些参数组合可能失败
      }
      optProgress.done++
    }

    // 按收益率排序
    results.sort((a, b) => (b.pnl_pct || 0) - (a.pnl_pct || 0))
    optAllResults.value = results

    if (results.length > 0) {
      optBestResult.value = results[0]
      optBestParams.value = results[0].params || {}
      ElMessage.success(`优化完成: ${results.length} 次回测, 最优收益 ${(results[0].pnl_pct || 0).toFixed(2)}%`)
    } else {
      ElMessage.warning('所有参数组合均失败')
    }
  } catch (e) { ElMessage.error(e.message) }
  finally {
    running.value = false
    optProgress.total = 0
    optProgress.done = 0
  }
}

// 生成参数组合 (递归笛卡尔积)
function generateCombinations() {
  const keys = optParams.value.map(p => p.key)
  const values = optParams.value.map(p => {
    const vals = []
    for (let v = p.min; v <= p.max; v += p.step) {
      vals.push(Math.round(v * 100) / 100)
    }
    return vals
  })

  function cartesian(arrays) {
    return arrays.reduce((acc, curr) => {
      const result = []
      for (const a of acc) {
        for (const c of curr) {
          result.push([...a, c])
        }
      }
      return result
    }, [[]])
  }

  if (values.length === 0) return []
  return cartesian(values).map(combo => {
    const obj = {}
    keys.forEach((k, i) => { obj[k] = combo[i] })
    return obj
  })
}

// =============================================
// AI 预测 / 回测(Kronos)
// =============================================
const kronosStatus = ref({
  available: false, loaded: false,
  model_name: null, device: null,
  models: [], default: 'kronos-mini',
  error: null,
})
const kronosLoading = ref(false)
const predicting = ref(false)
const aiResult = ref(null)
const aiChartRef = ref(null)
let aiChart = null

const aiForm = reactive({
  code: '000001',
  adjust: 'qfq',
  model: 'kronos-base',
  lookback: 200,
  pred_len: 20,
  temperature: 1.0,
  top_p: 0.9,
  sample_count: 1,
  train_end: '',
})

const aiBacktestRows = computed(() => {
  if (!aiResult.value || !aiResult.value.actual || !aiResult.value.prediction) return []
  const predMap = {}
  for (const p of aiResult.value.prediction) {
    predMap[p.trade_date] = p
  }
  const rows = []
  let prevPred = null, prevActual = null
  for (const a of aiResult.value.actual) {
    const p = predMap[a.trade_date]
    if (!p) continue
    const cp = Number(p.close)
    const ca = Number(a.close)
    const error_pct = ((cp - ca) / ca) * 100
    const dir_pred = prevPred == null ? 0 : (cp > prevPred ? 1 : (cp < prevPred ? -1 : 0))
    const dir_actual = prevActual == null ? 0 : (ca > prevActual ? 1 : (ca < prevActual ? -1 : 0))
    rows.push({
      trade_date: a.trade_date,
      close_pred: cp, close_actual: ca,
      error_pct,
      hit: dir_pred !== 0 && dir_pred === dir_actual,
    })
    prevPred = cp; prevActual = ca
  }
  return rows
})

function aiEnsureChart() {
  if (aiChart) return aiChart
  if (!aiChartRef.value) return null
  aiChart = echarts.init(aiChartRef.value)
  window.addEventListener('resize', aiResize)
  return aiChart
}
function aiResize() { aiChart && aiChart.resize() }

async function loadKronosStatus() {
  try { kronosStatus.value = await kronosApi.status() }
  catch (e) { ElMessage.error(e.message) }
}

async function kronosLoadModel() {
  kronosLoading.value = true
  try {
    ElMessage.info('开始加载模型...')
    const s = await kronosApi.load(aiForm.model)
    kronosStatus.value = s
    ElMessage.success(`模型 ${s.model_name} 已加载`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally { kronosLoading.value = false }
}

async function kronosUnloadModel() {
  kronosLoading.value = true
  try {
    await kronosApi.unload()
    await loadKronosStatus()
    ElMessage.success('已卸载')
  } catch (e) { ElMessage.error(e.message) }
  finally { kronosLoading.value = false }
}

function useRecentPreset() {
  const now = new Date()
  const trainEnd = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
  aiForm.train_end = trainEnd.toISOString().slice(0, 10)
  ElMessage.success(`已设置:训练截止 ${aiForm.train_end}`)
}

async function runPredictCommon({ withBacktest }) {
  if (!aiForm.code) return ElMessage.warning('请输入股票代码')
  if (withBacktest && !aiForm.train_end) {
    return ElMessage.warning('回测模式必须选择「训练截止日」,或点上方"推荐"按钮自动填')
  }
  predicting.value = true
  try {
    const payload = {
      code: aiForm.code,
      lookback: aiForm.lookback,
      pred_len: aiForm.pred_len,
      adjust: aiForm.adjust,
      temperature: aiForm.temperature,
      top_p: aiForm.top_p,
      sample_count: aiForm.sample_count,
    }
    if (withBacktest) {
      payload.train_end = aiForm.train_end
      payload.compare_actual = true
    }
    const r = await kronosApi.predict(payload)
    aiResult.value = r
    ElMessage.success(
      withBacktest
        ? `回测完成:方向正确率 ${r.metrics?.direction_accuracy}%`
        : '预测完成'
    )
    await nextTick()
    renderAiChart()
  } catch (e) {
    ElMessage.error(e.message)
  } finally { predicting.value = false }
}

function runPredictSimple() { runPredictCommon({ withBacktest: false }) }
function runPredictBacktest() { runPredictCommon({ withBacktest: true }) }

function renderAiChart() {
  const c = aiEnsureChart()
  if (!c) return
  if (!aiResult.value) { c.clear(); return }

  const isBacktest = aiResult.value.mode === 'backtest'
  const hist = aiResult.value.history || []
  const pred = aiResult.value.prediction || []
  const actual = aiResult.value.actual || []

  const allDates = Array.from(new Set([
    ...hist.map(r => r.trade_date),
    ...pred.map(r => r.trade_date),
    ...actual.map(r => r.trade_date),
  ])).sort()

  const histMap = {}; hist.forEach(r => histMap[r.trade_date] = r)
  const predMap = {}; pred.forEach(r => predMap[r.trade_date] = r)
  const actualMap = {}; actual.forEach(r => actualMap[r.trade_date] = r)

  const toOHLC = (map) => allDates.map(d => {
    const r = map[d]
    return r ? [Number(r.open), Number(r.close), Number(r.low), Number(r.high)] : '-'
  })
  const toClose = (map) => allDates.map(d => {
    const r = map[d]
    return r ? Number(r.close) : null
  })

  const series = [
    {
      name: '历史K线', type: 'candlestick', data: toOHLC(histMap),
      itemStyle: { color: '#f56c6c', color0: '#67c23a', borderColor: '#f56c6c', borderColor0: '#67c23a' },
    },
  ]
  if (isBacktest && actual.length) {
    series.push({
      name: '实际K线', type: 'candlestick', data: toOHLC(actualMap),
      itemStyle: { color: '#909399', color0: '#c0c9d6', borderColor: '#606266', borderColor0: '#909399' },
    })
  }
  series.push({
    name: '预测K线', type: 'candlestick', data: toOHLC(predMap),
    itemStyle: { color: 'transparent', color0: 'transparent', borderColor: '#E6A23C', borderColor0: '#E6A23C' },
  })
  series.push({
    name: '预测收盘', type: 'line', data: toClose(predMap),
    lineStyle: { width: 2, color: '#E6A23C', type: 'dashed' },
    showSymbol: true, symbolSize: 6, itemStyle: { color: '#E6A23C' },
  })

  const T = chartThemeColors()
  c.setOption({
    textStyle: { color: T.text },
    title: {
      text: isBacktest ? `${aiResult.value.code} AI 回测对比` : `${aiResult.value.code} K线预测`,
      left: 'center',
      textStyle: { color: T.text },
    },
    legend: { data: ['历史K线', '实际K线', '预测K线', '预测收盘'], top: 30, textStyle: { color: T.subText } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' },
      backgroundColor: T.tooltipBg, borderColor: T.tooltipBorder, textStyle: { color: T.text } },
    grid: [{ left: 60, right: 30, top: 80, height: '65%' }],
    xAxis: { type: 'category', data: allDates, scale: true, boundaryGap: false,
      axisLine: { lineStyle: { color: T.axisLine } }, axisLabel: { color: T.subText } },
    yAxis: { scale: true, splitArea: { show: true }, axisLabel: { color: T.subText }, axisLine: { lineStyle: { color: T.axisLine } }, splitLine: { lineStyle: { color: T.splitLine } } },
    dataZoom: [
      { type: 'inside', start: 60, end: 100 },
      { show: true, type: 'slider', bottom: 10, start: 60, end: 100 },
    ],
    series,
  }, true)
}

watch(mode, async (newMode) => {
  // 切到 AI Tab 时拉取模型状态
  if (newMode === 'ai_simple' || newMode === 'ai_backtest') {
    await loadKronosStatus()
    await nextTick()
    aiEnsureChart()
    if (aiResult.value) renderAiChart()
  }
})

onMounted(() => {
  if (route.query.code) form.code = route.query.code
  if (route.query.strategy) {
    mode.value = 'single'
    const s = getStrategy(route.query.strategy)
    if (s) {
      if (s.type === 'sma') form.strategy = 'sma'
      else if (s.type === 'momentum') form.strategy = 'momentum'
      else if (s.type === 'buy_hold') form.strategy = 'buy_hold'
      else form.strategy = 'sma'
      for (const p of s.params || []) {
        if (p.key in form) form[p.key] = p.default
      }
    }
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', aiResize)
  if (aiChart) { aiChart.dispose(); aiChart = null }
})
</script>

<style scoped>
.strategy-checkboxes {
  display: flex; flex-direction: column; gap: var(--space-sm);
}
.strategy-checkboxes :deep(.el-checkbox) {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border-color-light);
  border-radius: var(--radius-md);
  margin-right: 0;
  transition: all var(--transition-fast);
}
.strategy-checkboxes :deep(.el-checkbox:hover) {
  border-color: var(--color-primary-lighter);
}
.strategy-checkboxes :deep(.el-checkbox.is-checked) {
  border-color: var(--color-primary);
  background: var(--bg-active);
}
.cb-name {
  font-weight: var(--font-medium); margin-right: var(--space-sm);
}
.cb-desc {
  color: var(--text-secondary); font-size: var(--text-xs);
}

.params-editor {
  display: flex; flex-direction: column; gap: var(--space-sm);
}
.param-opt-row {
  display: flex; align-items: center; gap: var(--space-sm);
  flex-wrap: wrap;
}
.param-label {
  font-weight: var(--font-medium); min-width: 80px; color: var(--text-regular);
}

:deep(.best-row) {
  background: var(--color-success-light) !important;
}
</style>
