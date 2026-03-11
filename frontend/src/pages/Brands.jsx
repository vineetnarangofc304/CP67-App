import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../App';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { toast } from 'sonner';
import { 
  Store, 
  Plus, 
  Edit, 
  Trash2, 
  Search,
  IndianRupee,
  TrendingUp,
  Upload,
  History,
  FileSpreadsheet,
  RefreshCw
} from 'lucide-react';

const Brands = () => {
  const { token, API_URL } = useAuth();
  const [brands, setBrands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [selectedBrand, setSelectedBrand] = useState(null);
  const [formData, setFormData] = useState({ brand_name: '', atv: '', category: '' });
  const [uploading, setUploading] = useState(false);
  const [uploadHistory, setUploadHistory] = useState([]);
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchBrands();
  }, []);

  const fetchBrands = async () => {
    try {
      const response = await fetch(`${API_URL}/admin/brands`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setBrands(data.brands);
      }
    } catch (error) {
      toast.error('Failed to fetch brands');
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!formData.brand_name.trim()) {
      toast.error('Brand name is required');
      return;
    }

    try {
      const response = await fetch(`${API_URL}/admin/brands`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          brand_name: formData.brand_name.trim(),
          atv: parseFloat(formData.atv) || 0,
          category: formData.category.trim() || null
        })
      });

      if (response.ok) {
        toast.success('Brand added successfully');
        setShowAddDialog(false);
        setFormData({ brand_name: '', atv: '', category: '' });
        fetchBrands();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to add brand');
      }
    } catch (error) {
      toast.error('Failed to add brand');
    }
  };

  const handleEdit = async () => {
    if (!selectedBrand) return;

    try {
      const response = await fetch(`${API_URL}/admin/brands/${selectedBrand.id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          brand_name: formData.brand_name.trim(),
          atv: parseFloat(formData.atv) || 0,
          category: formData.category.trim() || null
        })
      });

      if (response.ok) {
        toast.success('Brand updated successfully');
        setShowEditDialog(false);
        setSelectedBrand(null);
        setFormData({ brand_name: '', atv: '', category: '' });
        fetchBrands();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to update brand');
      }
    } catch (error) {
      toast.error('Failed to update brand');
    }
  };

  const handleDelete = async (brand) => {
    if (!confirm(`Are you sure you want to delete "${brand.brand_name}"?`)) return;

    try {
      const response = await fetch(`${API_URL}/admin/brands/${brand.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        toast.success('Brand deleted');
        fetchBrands();
      } else {
        toast.error('Failed to delete brand');
      }
    } catch (error) {
      toast.error('Failed to delete brand');
    }
  };

  const openEditDialog = (brand) => {
    setSelectedBrand(brand);
    setFormData({
      brand_name: brand.brand_name,
      atv: brand.atv.toString(),
      category: brand.category || ''
    });
    setShowEditDialog(true);
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const validTypes = ['.xlsx', '.xls', '.csv'];
    const fileExt = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!validTypes.includes(fileExt)) {
      toast.error('Please upload an Excel (.xlsx) or CSV file');
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_URL}/admin/brands/upload-excel`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });

      const data = await response.json();
      
      if (response.ok && data.success) {
        toast.success(`Imported ${data.imported} new, updated ${data.updated} existing brands`);
        fetchBrands();
        fetchUploadHistory();
      } else {
        toast.error(data.message || data.detail || 'Upload failed');
      }
    } catch (error) {
      toast.error('Failed to upload file');
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const fetchUploadHistory = async () => {
    try {
      const response = await fetch(`${API_URL}/admin/brands/upload-history`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setUploadHistory(data.history || []);
      }
    } catch (error) {
      console.error('Failed to fetch upload history');
    }
  };

  const openHistoryDialog = () => {
    fetchUploadHistory();
    setShowHistoryDialog(true);
  };

  const filteredBrands = brands.filter(brand =>
    brand.brand_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalAtv = brands.reduce((sum, b) => sum + (b.atv || 0), 0);
  const avgAtv = brands.length > 0 ? totalAtv / brands.length : 0;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Brand Configuration</h1>
            <p className="text-slate-500">Manage brands and their Average Transaction Value (ATV)</p>
          </div>
          <div className="flex gap-2">
            <input
              type="file"
              ref={fileInputRef}
              accept=".xlsx,.xls,.csv"
              onChange={handleFileUpload}
              className="hidden"
            />
            <Button 
              variant="outline" 
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? (
                <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Uploading...</>
              ) : (
                <><Upload className="h-4 w-4 mr-2" />Upload Excel</>
              )}
            </Button>
            <Button variant="outline" onClick={openHistoryDialog}>
              <History className="h-4 w-4 mr-2" />
              History
            </Button>
            <Button onClick={() => setShowAddDialog(true)} className="bg-blue-600 hover:bg-blue-700">
              <Plus className="h-4 w-4 mr-2" />
              Add Brand
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Store className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{brands.length}</p>
                  <p className="text-sm text-slate-500">Total Brands</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                  <IndianRupee className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">₹{avgAtv.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</p>
                  <p className="text-sm text-slate-500">Average ATV</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                  <TrendingUp className="h-5 w-5 text-purple-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">₹{Math.max(...brands.map(b => b.atv || 0)).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</p>
                  <p className="text-sm text-slate-500">Highest ATV</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Search & Table */}
        <Card className="border-slate-200 shadow-none">
          <CardHeader className="pb-4">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <CardTitle className="text-lg">All Brands</CardTitle>
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  placeholder="Search brands..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8 text-slate-500">Loading...</div>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Brand Name</TableHead>
                      <TableHead className="text-right">ATV (₹)</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredBrands.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center py-8 text-slate-500">
                          {searchQuery ? 'No brands match your search' : 'No brands found'}
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredBrands.map((brand) => (
                        <TableRow key={brand.id}>
                          <TableCell className="font-medium">{brand.brand_name}</TableCell>
                          <TableCell className="text-right font-mono">
                            {brand.atv ? `₹${brand.atv.toLocaleString('en-IN')}` : '-'}
                          </TableCell>
                          <TableCell>{brand.category || '-'}</TableCell>
                          <TableCell>
                            <Badge variant={brand.is_active ? 'default' : 'secondary'}>
                              {brand.is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openEditDialog(brand)}
                              >
                                <Edit className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-red-600 hover:text-red-700"
                                onClick={() => handleDelete(brand)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Add Brand Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add New Brand</DialogTitle>
            <DialogDescription>
              Add a new brand with its Average Transaction Value
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Brand Name *</Label>
              <Input
                value={formData.brand_name}
                onChange={(e) => setFormData({ ...formData, brand_name: e.target.value })}
                placeholder="Enter brand name"
              />
            </div>
            <div className="space-y-2">
              <Label>ATV (Average Transaction Value) ₹</Label>
              <Input
                type="number"
                value={formData.atv}
                onChange={(e) => setFormData({ ...formData, atv: e.target.value })}
                placeholder="0"
              />
            </div>
            <div className="space-y-2">
              <Label>Category (Optional)</Label>
              <Input
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                placeholder="e.g., Food, Fashion, Electronics"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)}>Cancel</Button>
            <Button onClick={handleAdd}>Add Brand</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Brand Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Brand</DialogTitle>
            <DialogDescription>
              Update brand details and ATV
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Brand Name *</Label>
              <Input
                value={formData.brand_name}
                onChange={(e) => setFormData({ ...formData, brand_name: e.target.value })}
                placeholder="Enter brand name"
              />
            </div>
            <div className="space-y-2">
              <Label>ATV (Average Transaction Value) ₹</Label>
              <Input
                type="number"
                value={formData.atv}
                onChange={(e) => setFormData({ ...formData, atv: e.target.value })}
                placeholder="0"
              />
            </div>
            <div className="space-y-2">
              <Label>Category (Optional)</Label>
              <Input
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                placeholder="e.g., Food, Fashion, Electronics"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>Cancel</Button>
            <Button onClick={handleEdit}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="h-5 w-5" />
              Upload History
            </DialogTitle>
            <DialogDescription>
              Recent brand file uploads
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            {uploadHistory.length === 0 ? (
              <p className="text-center text-slate-500 py-8">No upload history found</p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {uploadHistory.map((record) => (
                  <div key={record.id} className="p-3 border rounded-lg bg-slate-50">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <FileSpreadsheet className="h-4 w-4 text-green-600" />
                        <span className="font-medium">{record.filename}</span>
                      </div>
                      <Badge variant="outline">{record.brands_in_file} brands</Badge>
                    </div>
                    <div className="mt-2 text-sm text-slate-600 grid grid-cols-2 gap-2">
                      <div>New: <span className="font-semibold text-green-600">{record.imported}</span></div>
                      <div>Updated: <span className="font-semibold text-blue-600">{record.updated}</span></div>
                      <div>By: {record.uploaded_by}</div>
                      <div>{new Date(record.uploaded_at).toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowHistoryDialog(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default Brands;
